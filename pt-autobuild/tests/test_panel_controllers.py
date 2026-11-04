"""
Tests de los controladores del panel (sin tkinter) y del runner de acciones.

pyautogui esta bloqueado por conftest: si algun camino intentara mover el mouse de verdad, el
test fallaria. Las funciones de automation/ se sustituyen por registradores cuando se quiere
comprobar CON QUE argumentos las llama el controlador (sobre todo dry_run).
"""

import ast
import glob
import inspect
import json
import os
import threading

import pytest

from automation import build, calibrate, configure_ip, configure_router, move_device
from core import autocalibrate as ac
from core import paths, settings
from core.errors import PTError
from panel.controllers import Shared
from panel.controllers import ajustes as ajustes_mod
from panel.controllers import calibracion as calibracion_mod
from panel.controllers import colocar as colocar_mod
from panel.controllers import configurar as configurar_mod
from panel.controllers.ajustes import AjustesController
from panel.controllers.calibracion import CalibracionController
from panel.controllers.colocar import ColocarController
from panel.controllers.configurar import ConfigurarController
from panel.controllers.runner import ActionRunner

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COORDS = {"search_field": [300, 1000], "filtered_result": [200, 950],
          "canvas": {"top_left": [12, 150], "bottom_right": [1800, 800]}}
GROUPED = ("SWITCHES: Sw1\nROUTERS: R01\nRED Red1: 192.168.10.0/24 R01\n"
           "PC1 .2\nPC2\n")


@pytest.fixture
def shared():
    return Shared(ActionRunner(sync=True, tick_seconds=0), countdown=0)


def logs(shared):
    return [e[1] for e in shared.runner.drain() if e[0] == "log"]


def events(shared):
    return shared.runner.drain()


@pytest.fixture
def calibrated(isolated_data_dir):
    os.makedirs(paths.DATA_DIR, exist_ok=True)
    with open(paths.COORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(COORDS, f)


@pytest.fixture
def registry(calibrated):
    os.makedirs(os.path.dirname(paths.TOPOLOGY_ACTUAL_PATH), exist_ok=True)
    topo = {"dispositivos": [
        {"id": 1, "tipo": "router", "modelo": "4331", "nombre": "R01", "posicion": [400, 200]},
        {"id": 2, "tipo": "end_device", "modelo": "PC", "nombre": "PC1", "posicion": [500, 400],
         "ip": "192.168.10.2", "mascara": "255.255.255.0", "gateway": "192.168.10.1"},
        {"id": 3, "tipo": "end_device", "modelo": "PC", "nombre": "PC2", "posicion": [600, 400]},
    ]}
    with open(paths.TOPOLOGY_ACTUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(topo, f)


class Recorder:
    """Sustituye una funcion de automation/ y guarda con que se la llamo."""

    def __init__(self, shared=None, result=None):
        self.calls = []
        self.mouse_flags = []
        self.shared = shared
        self.result = result

    def __call__(self, *a, **k):
        self.calls.append((a, k))
        if self.shared is not None:
            self.mouse_flags.append(self.shared.runner.touches_mouse)
        return self.result


# =====================================================================
# ActionRunner
# =====================================================================
def test_runner_ok_y_eventos():
    r = ActionRunner(sync=True)
    assert r.start("accion", lambda ctx: ctx.log("hola"))
    ev = r.drain()
    kinds = [e[0] for e in ev]
    assert kinds[0] == "state" and "done" in kinds and ev[-1] == ("done", "ok", "accion")
    assert any(e == ("log", "hola") for e in ev)
    assert not r.busy


def test_runner_pterror_se_muestra_sin_traza():
    r = ActionRunner(sync=True)

    def boom(ctx):
        raise PTError("algo claro")

    r.start("x", boom)
    ev = r.drain()
    assert ("done", "error", "x") in ev
    assert any(e[0] == "log" and e[1] == "[ERROR] algo claro" for e in ev)
    assert not any("Traceback" in str(e) for e in ev)


def test_runner_error_inesperado_guarda_traza_en_archivo(isolated_data_dir):
    r = ActionRunner(sync=True)

    def boom(ctx):
        raise RuntimeError("fallo raro")

    r.start("x", boom)
    ev = r.drain()
    assert any(e[0] == "log" and e[1].startswith("[ERROR inesperado] RuntimeError") for e in ev)
    assert not any("Traceback" in str(e) for e in ev)
    with open(os.path.join(paths.DATA_DIR, "panel_errors.log"), encoding="utf-8") as f:
        assert "RuntimeError: fallo raro" in f.read()


def test_runner_cancelacion_en_la_accion():
    r = ActionRunner(sync=True)

    def job(ctx):
        r.cancel.set()
        from panel.controllers.runner import CancelledError
        raise CancelledError("parado")

    r.start("x", job)
    assert ("done", "cancelled", "x") in r.drain()


def test_runner_detener_durante_la_cuenta_regresiva_no_ejecuta_la_accion():
    r = ActionRunner(tick_seconds=0.2)
    ran = []
    r.start("x", lambda ctx: ran.append(1), touches_mouse=True, countdown=5)
    r.stop()
    r.join(5)
    assert ran == []
    ev = r.drain()
    assert ("done", "cancelled", "x") in ev
    assert any(e[0] == "tick" for e in ev)                # la cuenta regresiva fue visible


def test_runner_cuenta_regresiva_visible_y_failsafe_activo():
    import pyautogui
    pyautogui.FAILSAFE = False
    r = ActionRunner(sync=True, tick_seconds=0)
    r.start("x", lambda ctx: None, touches_mouse=True, countdown=3)
    ticks = [e[1] for e in r.drain() if e[0] == "tick"]
    assert ticks == [3, 2, 1, 0]
    assert pyautogui.FAILSAFE is True


def test_runner_sin_mouse_no_hace_cuenta_regresiva():
    r = ActionRunner(sync=True, tick_seconds=0)
    r.start("x", lambda ctx: None, touches_mouse=False, countdown=5)
    assert [e for e in r.drain() if e[0] == "tick"] == []


def test_runner_rechaza_segunda_accion_en_paralelo():
    r = ActionRunner()
    gate = threading.Event()
    assert r.start("a", lambda ctx: gate.wait(5))
    assert r.start("b", lambda ctx: None) is False
    gate.set()
    r.join(5)
    assert not r.busy
    assert any(e[0] == "log" and "ya hay una accion" in e[1] for e in r.drain())


def test_runner_failsafe_exception_se_reporta_como_detenido():
    r = ActionRunner(sync=True)

    class FailSafeException(Exception):
        pass

    def job(ctx):
        raise FailSafeException()

    r.start("x", job)
    ev = r.drain()
    assert ("done", "cancelled", "x") in ev
    assert any("FAILSAFE" in str(e) for e in ev)


# =====================================================================
# Colocar
# =====================================================================
def test_colocar_ejemplos_y_carga_de_archivos(shared, tmp_path):
    c = ColocarController(shared)
    names = c.list_examples()
    assert "redes.txt" in names and "redes2.txt" in names
    assert "SWITCHES" in c.load_example("redes.txt")
    j = tmp_path / "t.json"
    j.write_text(json.dumps({"comando_original": "2 routers"}))
    assert c.load_file(str(j)) == "2 routers"
    j.write_text(json.dumps({"topologia": "3 PC"}))
    assert c.load_file(str(j)) == "3 PC"
    j.write_text(json.dumps({"otra": 1}))
    with pytest.raises(PTError):
        c.load_file(str(j))
    j.write_text("{roto")
    with pytest.raises(PTError):
        c.load_file(str(j))
    with pytest.raises(PTError):
        c.load_file(str(tmp_path / "no_existe.txt"))


def test_colocar_ejemplo_del_registro_de_la_herramienta(shared):
    # config/topologia_ejemplo.json lleva 'comando_original'
    c = ColocarController(shared)
    text = c.load_file(paths.TOPOLOGY_EXAMPLE_PATH)
    assert text.strip()


def test_colocar_preview(shared, calibrated):
    c = ColocarController(shared)
    res = c.preview("2 routers, 1 switch, 3 PC")
    assert res.ok and "DRY-RUN" in res.text()
    bad = c.preview("tonteria")
    assert not bad.ok and bad.error


def test_colocar_preview_sin_calibrar(shared):
    res = ColocarController(shared).preview("2 routers")
    assert not res.ok and "Calibra" in res.error


def test_colocar_build_por_defecto_es_dry_run_y_no_mueve_el_mouse(shared, calibrated):
    c = ColocarController(shared)
    out = c.build("2 routers, 1 switch")            # dry_run=True por defecto
    assert out.status == "started"
    assert any("DRY-RUN" in line for line in logs(shared))     # y pyautogui bloqueado: no clic


def test_colocar_build_real_bloqueado_si_falta_calibrar(shared, monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(build, "build_topology", rec)
    c = ColocarController(shared)
    out = c.build("2 routers", dry_run=False)
    assert out.status == "blocked" and not out.preflight.ok
    assert "search_field" in out.preflight.blocking
    assert rec.calls == []                                   # no actuo
    assert events(shared) == []                              # ni siquiera se arranco una accion


def test_colocar_build_real_pasa_flags_y_hace_cuenta_regresiva(shared, calibrated, monkeypatch):
    shared.countdown = 4
    rec = Recorder(shared)
    monkeypatch.setattr(build, "build_topology", rec)
    c = ColocarController(shared)
    out = c.build("2 routers", dry_run=False)
    assert out.status == "started"
    (a, k), = rec.calls
    assert k["dry_run"] is False and k["countdown"] == 0 and "cancel" in k and "progress" in k
    assert rec.mouse_flags == [True]
    assert [e[1] for e in events(shared) if e[0] == "tick"] == [4, 3, 2, 1, 0]


def test_colocar_build_dry_no_marca_mouse_ni_cuenta_regresiva(shared, calibrated, monkeypatch):
    shared.countdown = 4
    rec = Recorder(shared)
    monkeypatch.setattr(build, "build_topology", rec)
    ColocarController(shared).build("2 routers")
    (a, k), = rec.calls
    assert k["dry_run"] is True and rec.mouse_flags == [False]
    assert [e for e in events(shared) if e[0] == "tick"] == []


def test_colocar_build_texto_vacio(shared):
    with pytest.raises(PTError):
        ColocarController(shared).build("   ")


def test_colocar_recalibrar_y_continuar_por_defecto_es_dry_run(shared, calibrated, monkeypatch):
    cal, bld = Recorder(), Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", cal)
    monkeypatch.setattr(build, "build_topology", bld)
    c = ColocarController(shared)
    c.last_preflight = None
    assert c.recalibrate_and_continue("2 routers") is True
    (a, k), = cal.calls
    assert k["dry_run"] is True
    assert bld.calls == []                                   # en dry-run no construye


def test_colocar_recalibrar_real_construye_si_queda_calibrado(shared, calibrated, monkeypatch):
    cal, bld = Recorder(), Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", cal)
    monkeypatch.setattr(build, "build_topology", bld)
    c = ColocarController(shared)
    c.recalibrate_and_continue("2 routers", dry_run=False)
    assert cal.calls[0][1]["dry_run"] is False
    assert bld.calls and bld.calls[0][1]["dry_run"] is False


def test_colocar_recalibrar_real_falla_si_sigue_sin_calibrar(shared, monkeypatch):
    monkeypatch.setattr(calibrate, "auto_calibrate", Recorder())
    bld = Recorder()
    monkeypatch.setattr(build, "build_topology", bld)
    ColocarController(shared).recalibrate_and_continue("2 routers", dry_run=False)
    assert bld.calls == []
    assert any("sigue sin estar calibrado" in line for line in logs(shared))


def test_colocar_preflight_con_ips_exige_los_puntos_ip(shared, calibrated):
    c = ColocarController(shared)
    result, _ = c.check_preflight(GROUPED)
    assert "ipv4_address" in result.blocking
    result2, _ = c.check_preflight("2 routers")
    assert "ipv4_address" not in [n for n, _s, _d in result2.items]


def test_colocar_mover_dispositivo(shared, registry, monkeypatch):
    rec = Recorder(shared)
    monkeypatch.setattr(move_device, "move_device", rec)
    c = ColocarController(shared)
    assert c.list_devices() == ["R01", "PC1", "PC2"]
    c.move_device("R01", "600", "300")
    (a, k), = rec.calls
    assert k["dry_run"] is True and rec.mouse_flags == [False]
    with pytest.raises(PTError):
        c.move_device("", 1, 1)
    with pytest.raises(PTError):
        c.move_device("R01", "abc", "1")


def test_colocar_mover_real_cuenta_regresiva(shared, registry, monkeypatch):
    shared.countdown = 2
    rec = Recorder(shared)
    monkeypatch.setattr(move_device, "move_device", rec)
    ColocarController(shared).move_device("R01", 600, 300, dry_run=False)
    assert rec.calls[0][1]["dry_run"] is False and rec.mouse_flags == [True]
    assert [e[1] for e in events(shared) if e[0] == "tick"] == [2, 1, 0]


# =====================================================================
# Configurar
# =====================================================================
def test_configurar_generar_config(shared):
    c = ConfigurarController(shared)
    res = c.generate_config(GROUPED, "Estatico")
    assert res.configs and "interface" in res.text() and "ip address 192.168.10.1" in res.text()
    res_rip = c.generate_config(GROUPED, "RIP")
    assert "router rip" in res_rip.text()
    text = open(os.path.join(paths.EXAMPLES_DIR, "redes2.txt"), encoding="utf-8").read()
    assert c.generate_config(text, "Estatico").text()      # ejemplo incompleto: avisos, sin fallar
    with pytest.raises(PTError):
        c.generate_config("", "Estatico")
    with pytest.raises(PTError):
        c.generate_config("SWITCHES: A, A", "Estatico")
    with pytest.raises(PTError):
        c.generate_config(text, "Otro")


def test_configurar_listas_y_datos(shared, registry):
    c = ConfigurarController(shared)
    assert c.list_pcs() == ["PC1", "PC2"] and c.list_routers() == ["R01"]
    assert c.device_ip_data("PC1") == ("192.168.10.2", "255.255.255.0", "192.168.10.1")
    assert c.device_ip_data("nadie") == ("", "", "")
    assert [d["nombre"] for d in c.pcs_with_ip()] == ["PC1"]


def test_configurar_sin_registro(shared, isolated_data_dir):
    c = ConfigurarController(shared)
    assert c.list_pcs() == [] and c.list_routers() == []


def test_configurar_ip_dry_run_por_defecto(shared, registry, monkeypatch):
    rec = Recorder(shared)
    monkeypatch.setattr(configure_ip, "configure_device_ip", rec)
    ConfigurarController(shared).apply_ip("PC1", "10.0.0.2", "255.255.255.0", "10.0.0.1")
    (a, k), = rec.calls
    assert k["dry_run"] is True and rec.mouse_flags == [False]


def test_configurar_ip_real_con_cuenta_regresiva(shared, registry, monkeypatch):
    shared.countdown = 3
    rec = Recorder(shared)
    monkeypatch.setattr(configure_ip, "configure_device_ip", rec)
    ConfigurarController(shared).apply_ip("PC1", "10.0.0.2", "255.255.255.0", "10.0.0.1",
                                          dry_run=False)
    assert rec.calls[0][1]["dry_run"] is False and rec.mouse_flags == [True]
    assert [e[1] for e in events(shared) if e[0] == "tick"] == [3, 2, 1, 0]


def test_configurar_ip_todas(shared, registry, monkeypatch):
    rec = Recorder(shared)
    monkeypatch.setattr(configure_ip, "configure_device_ip", rec)
    c = ConfigurarController(shared)
    c.apply_all_ips()
    assert len(rec.calls) == 1 and rec.calls[0][0][0] == "PC1"      # solo PC1 trae IP
    assert rec.calls[0][1]["dry_run"] is True
    ev = events(shared)
    assert ("progress", 1, 1) in ev


def test_configurar_ip_todas_sin_pcs(shared, isolated_data_dir):
    with pytest.raises(PTError):
        ConfigurarController(shared).apply_all_ips()


def test_configurar_hostname_dry_run_por_defecto(shared, registry, monkeypatch):
    rec = Recorder(shared)
    monkeypatch.setattr(configure_router, "set_router_hostname", rec)
    ConfigurarController(shared).set_hostname("R01", "R01")
    assert rec.calls[0][1]["dry_run"] is True and rec.mouse_flags == [False]


def test_configurar_errores_reales_se_muestran_como_ptError(shared, registry):
    c = ConfigurarController(shared)
    c.apply_ip("PC1", "999.1.1.1", "255.255.255.0", "10.0.0.1")        # dry-run, IP invalida
    assert any("IPv4 valido" in line for line in logs(shared))


# =====================================================================
# Calibracion
# =====================================================================
def test_calibracion_instrucciones_segun_grupos(shared):
    c = CalibracionController(shared)
    assert "buscador" in c.instructions(["main"])
    t = c.instructions(["cable", "ip"])
    assert "rayo" in t and "IP Configuration" in t and "buscador" not in t
    assert "al menos un grupo" in c.instructions([])
    with pytest.raises(PTError):
        c.check_groups([])


def test_calibracion_ia_exige_api_key(shared, isolated_data_dir, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = CalibracionController(shared)
    for fn in (lambda: c.autocalibrate(["main"]), lambda: c.show_only(["main"]),
               lambda: c.force(["main"])):
        with pytest.raises(PTError) as ei:
            fn()
        assert "Ajustes" in str(ei.value)


@pytest.fixture
def with_key(isolated_data_dir, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings.save_settings("sk-ant-test-0000", "claude-sonnet-5-5")


def test_calibracion_modos_y_banderas(shared, with_key, monkeypatch):
    rec = Recorder(shared, result=0)
    monkeypatch.setattr(calibrate, "auto_calibrate", rec)
    chk = Recorder(shared, result=0)
    monkeypatch.setattr(calibrate, "check_calibration", chk)
    c = CalibracionController(shared)

    c.autocalibrate(["main"])                         # por defecto: dry-run
    c.show_only(["main", "cable"])
    c.autocalibrate(["main"], dry_run=False)
    c.force(["ip"])
    c.force(["ip"], dry_run=False)
    c.verify(["main"])
    flags = [(k["dry_run"], k["force"], k["groups"]) for _a, k in rec.calls]
    assert flags == [(True, False, ["main"]), (True, False, ["main", "cable"]),
                     (False, False, ["main"]), (True, True, ["ip"]), (False, True, ["ip"])]
    assert rec.mouse_flags == [False, False, True, False, True]
    assert chk.calls and rec.mouse_flags and chk.mouse_flags == [False]


def test_calibracion_estado_y_overlays(shared, calibrated):
    c = CalibracionController(shared)
    rows = c.status_rows()
    assert len(rows) == 16
    counts = c.status_counts(rows)
    assert counts["unverified"] == 4 and counts["manual"] == 12      # coords.json manual
    cal = dict((label, pts) for label, _c, pts in c.overlay_calibration())
    assert ("search_field", 300, 1000) in cal["coords.json"]
    assert ("canvas.top_left", 12, 150) in cal["coords.json"]
    with pytest.raises(PTError):
        c.overlay_topology()


def test_calibracion_iter_points_ignora_metadatos():
    pts = CalibracionController.iter_points(
        {"screen_size": [1, 2], "autocalibrate": {"resolution": [3, 4]}, "a": [5, 6],
         "b": {"c": [7, 8]}, "d": "skip", "e": [True, 1]})
    assert sorted(pts) == [("a", 5, 6), ("b.c", 7, 8)]


def test_calibracion_captura_manual(shared, monkeypatch):
    rec = Recorder(shared, result=[1, 2])
    monkeypatch.setattr(calibrate, "calibrate_point", rec)
    c = CalibracionController(shared)
    with pytest.raises(PTError):
        c.capture_point("nada")
    c.capture_point("canvas_top_left")
    assert rec.calls[0][0] == ("canvas_top_left",) and rec.mouse_flags == [False]
    with pytest.raises(PTError):
        c.capture_cable("", "R01")


def test_calibracion_captura_ip_router_cable_imagenes(shared, registry, monkeypatch):
    for mod, fname in ((configure_ip, "calibrate_ip_window"),
                       (configure_router, "calibrate_router"),
                       (calibrate, "calibrate_by_images")):
        monkeypatch.setattr(mod, fname, Recorder(shared, result=True))
    from automation import cable_link
    cable_rec = Recorder(shared, result={})
    monkeypatch.setattr(cable_link, "calibrate_cable", cable_rec)
    c = CalibracionController(shared)
    c.capture_ip_window()
    c.capture_router()
    c.calibrate_images()
    c.capture_cable("serial", "R01")
    assert cable_rec.calls[0][0] == ("serial", "R01")
    assert c.list_devices() == ["R01", "PC1", "PC2"]


# =====================================================================
# Ajustes
# =====================================================================
def test_ajustes_guardar_y_cargar_sin_filtrar_la_key(shared, isolated_data_dir, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    with open(paths.ENV_PATH, "w", encoding="utf-8") as f:
        f.write("# comentario\nOTRA=1\nANTHROPIC_MODEL=viejo\n")
    c = AjustesController(shared)
    secret = "sk-ant-api03-SECRETO-1234567890"
    msg = c.save(secret, "claude-sonnet-5-5")
    assert secret not in msg and "7890" in msg
    text = open(paths.ENV_PATH, encoding="utf-8").read()
    assert "OTRA=1" in text and "# comentario" in text
    assert f"ANTHROPIC_API_KEY={secret}" in text and "ANTHROPIC_MODEL=claude-sonnet-5-5" in text
    assert "viejo" not in text
    loaded = c.load()
    assert loaded["api_key"] == secret and loaded["model"] == "claude-sonnet-5-5"
    assert loaded["has_key"] is True


def test_ajustes_validaciones_no_incluyen_la_key(shared, isolated_data_dir):
    c = AjustesController(shared)
    with pytest.raises(PTError):
        c.save("", "m")
    with pytest.raises(PTError) as ei:
        c.save("clave con espacios", "m")
    assert "clave con espacios" not in str(ei.value)
    with pytest.raises(PTError):
        c.save("sk-ant-x", "")
    with pytest.raises(PTError):
        c.save("sk-ant-x", "mod elo!")
    assert not os.path.exists(paths.ENV_PATH)


def test_ajustes_probar_conexion_no_registra_la_key(shared, isolated_data_dir, monkeypatch):
    secret = "sk-ant-api03-OTRO-SECRETO-777"
    seen = {}

    def fake(key, model):
        seen["args"] = (key, model)
        return "Conexion correcta con la API (modelo m)."

    monkeypatch.setattr(ac, "test_connection", fake)
    AjustesController(shared).test_connection(secret, "m")
    out = "\n".join(logs(shared))
    assert seen["args"] == (secret, "m") and "Conexion correcta" in out and secret not in out


def test_ajustes_error_de_conexion_se_muestra_sin_la_key(shared, isolated_data_dir, monkeypatch):
    secret = "sk-ant-api03-TERCERA-555"

    def fake(key, model):
        raise ac.AutoCalibrateError("la API rechazo la clave (HTTP 401).")

    monkeypatch.setattr(ac, "test_connection", fake)
    AjustesController(shared).test_connection(secret, "m")
    out = "\n".join(logs(shared))
    assert "[ERROR] la API rechazo la clave" in out and secret not in out


def test_ajustes_informe_dpi(shared):
    ok, lines = AjustesController(shared).dpi_report()
    assert isinstance(ok, bool) and any("DPI awareness" in ln for ln in lines)


def test_test_connection_sin_red_o_clave(monkeypatch):
    with pytest.raises(ac.AutoCalibrateError):
        ac.test_connection("", "m")

    def fail(key, model, content, max_tokens=1024):
        raise ac.AutoCalibrateError("sin conexion")

    monkeypatch.setattr(ac, "call_api", fail)
    with pytest.raises(ac.AutoCalibrateError):
        ac.test_connection("k", "m")
    monkeypatch.setattr(ac, "call_api", lambda *a, **k: "ok")
    assert "Conexion correcta" in ac.test_connection("k", "")


# =====================================================================
# Auditoria de seguridad del panel
# =====================================================================
CONTROLLER_MODULES = (colocar_mod, configurar_mod, calibracion_mod, ajustes_mod)


def test_toda_accion_que_mueve_el_mouse_tiene_dry_run_true_por_defecto():
    total = 0
    for mod in CONTROLLER_MODULES:
        cls = next(v for k, v in vars(mod).items() if k.endswith("Controller")
                   and getattr(v, "__module__", "") == mod.__name__)
        for name in mod.MOUSE_ACTIONS:
            params = inspect.signature(getattr(cls, name)).parameters
            assert "dry_run" in params, f"{cls.__name__}.{name}"
            assert params["dry_run"].default is True, f"{cls.__name__}.{name}"
            total += 1
    assert total == 8


def test_las_vistas_pasan_dry_run_explicito_a_cada_accion_con_mouse():
    mouse_names = {n for mod in CONTROLLER_MODULES for n in mod.MOUSE_ACTIONS}
    mouse_names.discard("force")        # se comprueba abajo (nombre comun)
    mouse_names |= {"force"}
    offenders, found = [], 0
    for path in glob.glob(os.path.join(ROOT, "panel", "*.py")):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in mouse_names
                    and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "c"):
                found += 1
                if "dry_run" not in {kw.arg for kw in node.keywords}:
                    offenders.append(f"{os.path.basename(path)}:{node.lineno} {node.func.attr}")
    assert found >= 8
    assert offenders == []


def test_controladores_no_importan_tkinter_ni_las_vistas_automation():
    for path in glob.glob(os.path.join(ROOT, "panel", "controllers", "*.py")):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any(n.split(".")[0] in ("tkinter", "panel_view") for n in names), path
            assert not any(n == "panel" or n.startswith("panel.") and "controllers" not in n
                           for n in names), path
    for path in glob.glob(os.path.join(ROOT, "panel", "*.py")):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] != "automation", path


def test_ningun_archivo_de_panel_usa_print_ni_sys_exit():
    for path in glob.glob(os.path.join(ROOT, "panel", "**", "*.py"), recursive=True):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                assert not (isinstance(f, ast.Name) and f.id in ("print", "input")), path
                assert not (isinstance(f, ast.Attribute) and f.attr == "exit"), path


def test_los_archivos_viejos_ya_no_existen():
    assert not os.path.exists(os.path.join(ROOT, "panel", "panel_control.py"))
    assert not os.path.exists(os.path.join(ROOT, "automation", "_legacy_cli.py"))


# =====================================================================
# core.preflight (logica pura)
# =====================================================================
def test_preflight_evaluate_estados():
    from core import preflight
    rows = [{"name": "search_field", "status": "ok"},
            {"name": "filtered_result", "status": "unverified"},
            {"name": "canvas_top_left", "status": "manual"}]
    res = preflight.evaluate(rows, ["search_field", "filtered_result", "canvas_top_left",
                                    "canvas_bottom_right"])
    assert not res.ok
    assert res.blocking == ["canvas_top_left", "canvas_bottom_right"]   # y el que no existe
    assert res.warnings == ["filtered_result"]
    assert "canvas_top_left" in res.summary()
    ok = preflight.evaluate(rows[:2], ["search_field", "filtered_result"])
    assert ok.ok and "1 sin verificar" in ok.summary()


def test_preflight_ip_configuration_item_es_opcional():
    from core import preflight
    res = preflight.evaluate([], ["ip_configuration_item"])
    assert res.ok and res.warnings == ["ip_configuration_item"]


def test_preflight_nombres_requeridos():
    from core import preflight
    assert preflight.required_names("2 routers") == list(preflight.MAIN_NAMES)
    assert preflight.required_names("basura ???") == list(preflight.MAIN_NAMES)
    assert "ipv4_address" in preflight.required_names(GROUPED)
    assert preflight.groups_for(preflight.required_names(GROUPED)) == ("main", "ip")
    sin_ip = "SWITCHES: Sw1\nROUTERS: R01\nRED Red1: 192.168.10.0/24 R01\n"
    assert preflight.needs_ip_config(sin_ip) is False
