"""Boton unico "Calibrar", aviso en la cuenta regresiva y asistente por demanda (cable / ip)."""

import json
import os

import pytest

from automation import calibrate, configure_ip
from core import autocalibrate as ac
from core import paths, preflight
from core.errors import PTError
from panel.controllers import Shared
from panel.controllers.asistente import AsistenteController
from panel.controllers.calibracion import CalibracionController
from panel.controllers.configurar import ConfigurarController
from panel.controllers.runner import ActionRunner
from panel.controllers.simple import SimpleController
from tests.test_panel_controllers import (  # noqa: F401  (fixtures)
    CABLE_COORDS, COORDS, IP_COORDS, Recorder, calibrated, events, ip_calibrated, logs, registry)


@pytest.fixture
def shared():
    return Shared(ActionRunner(sync=True, tick_seconds=0), countdown=0)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "clave-de-prueba-123456")


def fake_check(monkeypatch, status):
    """Sustituye la verificacion en pantalla: todos los puntos main con ese estado."""
    calls = []

    def run_check(groups=ac.GROUPS, dry_run=False, log=None, table_out=None):
        calls.append({"groups": tuple(groups), "dry_run": dry_run})
        table_out.extend((n, "coords", status) for n in preflight.MAIN_NAMES)
        return 0 if status != "manual" else 1

    monkeypatch.setattr(ac, "run_check", run_check)
    return calls


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ===== Calibrar (pestana Simple y Avanzado) =====================================================
def test_calibrar_si_todo_coincide_dice_ya_calibrado_sin_api_ni_mouse(shared, monkeypatch):
    check = fake_check(monkeypatch, "ok")
    auto = Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", auto)
    assert SimpleController(shared).calibrate(dry_run=False)         # sin clave: no la necesita
    assert auto.calls == []
    assert check == [{"groups": ("main",), "dry_run": False}]
    text = "\n".join(logs(shared))
    assert "Ya está calibrado" in text and "Empezando" not in text


def test_calibrar_dry_run_verifica_pero_no_calibra_ni_guarda(shared, monkeypatch):
    check = fake_check(monkeypatch, "manual")
    auto = Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", auto)
    SimpleController(shared).calibrate()                              # dry_run=True por defecto
    assert auto.calls == [] and check[0]["dry_run"] is True
    text = "\n".join(logs(shared))
    assert "Dry-run" in text and "Voy a calibrar" in text
    assert "search_field" not in text and "buscador" in text


def test_calibrar_real_autocalibra_solo_main_y_avisa_antes_de_la_cuenta_regresiva(
        shared, with_key, monkeypatch):
    shared.countdown = 3
    fake_check(monkeypatch, "manual")
    seen = []

    def auto(**kw):
        seen.append((kw, shared.runner.touches_mouse))
        write(paths.COORDS_PATH, COORDS)

    monkeypatch.setattr(calibrate, "auto_calibrate", auto)
    SimpleController(shared).calibrate(dry_run=False)
    (kw, mouse), = seen
    assert kw["groups"] == ["main"] and kw["dry_run"] is False and mouse is True
    ev = events(shared)
    lines = [e[1] for e in ev if e[0] == "log"]
    warn = next(i for i, m in enumerate(lines) if "escribir un modelo de prueba" in m)
    first_tick = next(i for i, m in enumerate(lines) if "Empezando en 3" in m)
    assert warn < first_tick                                  # avisa ANTES de la cuenta regresiva
    assert [e[1] for e in ev if e[0] == "tick"] == [3, 2, 1, 0]
    text = "\n".join(lines)
    assert "Quedó bien" in text and "search_field" not in text


def test_calibrar_real_resume_lo_que_hay_que_hacer_a_mano(shared, with_key, monkeypatch):
    fake_check(monkeypatch, "manual")
    monkeypatch.setattr(calibrate, "auto_calibrate", lambda **kw: 1)   # no logra nada
    SimpleController(shared).calibrate(dry_run=False)
    text = "\n".join(logs(shared))
    assert "Hay que hacerlo a mano" in text and "F8" in text
    assert "Herramientas de depuración" in text
    assert "el buscador de dispositivos" in text and "search_field" not in text


def test_calibrar_real_sin_clave_no_calibra(shared, monkeypatch):
    fake_check(monkeypatch, "manual")
    auto = Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", auto)
    SimpleController(shared).calibrate(dry_run=False)
    assert auto.calls == [] and not shared.runner.busy
    assert "[ERROR] falta la clave de la IA" in "\n".join(logs(shared))


def test_calibrar_avanzado_es_el_mismo_boton(shared, monkeypatch):
    check = fake_check(monkeypatch, "ok")
    CalibracionController(shared).calibrate()
    assert check and "Ya está calibrado" in "\n".join(logs(shared))


def test_calibrar_estado_resumido(shared, calibrated):  # noqa: F811
    assert CalibracionController(shared).status_text() == "Calibración lista."
    os.remove(paths.COORDS_PATH)
    text = CalibracionController(shared).status_text()
    assert text.startswith("Falta calibrar") and "Calibrar" in text and "search_field" not in text


def test_otra_accion_en_curso_bloquea_calibrar(shared, monkeypatch):
    fake_check(monkeypatch, "ok")
    shared.runner.state = "running"
    assert SimpleController(shared).calibrate() is False


def test_runner_escribe_el_aviso_antes_de_la_cuenta_regresiva_solo_si_toca_el_mouse():
    r = ActionRunner(sync=True, tick_seconds=0)
    r.start("x", lambda ctx: None, touches_mouse=True, countdown=2, notice=["AVISO"])
    lines = [e[1] for e in r.drain() if e[0] == "log"]
    assert lines.index("AVISO") < next(i for i, m in enumerate(lines) if "Empezando en 2" in m)
    r.start("y", lambda ctx: None, touches_mouse=False, notice=["AVISO"])
    assert "AVISO" not in [e[1] for e in r.drain() if e[0] == "log"]


def test_toda_calibracion_que_escribe_en_el_buscador_avisa(shared, with_key, monkeypatch):
    monkeypatch.setattr(calibrate, "auto_calibrate", lambda **kw: 0)
    monkeypatch.setenv("OPENAI_MODEL", "modelo-vision-x")
    c = CalibracionController(shared)
    c.force(["main"], dry_run=False)
    assert any("escribir un modelo de prueba" in m for m in logs(shared))
    c.force(["ip"], dry_run=False)                       # ip no escribe en el buscador
    assert not any("escribir un modelo de prueba" in m for m in logs(shared))
    c.show_only(["main"])                                # dry-run no escribe
    assert not any("escribir un modelo de prueba" in m for m in logs(shared))


# ===== Asistente por demanda (ip y cable) ========================================================
def test_aplicar_ip_real_sin_calibrar_no_actua_y_deja_el_asistente(shared, registry,  # noqa: F811
                                                                   monkeypatch):
    rec = Recorder(shared)
    monkeypatch.setattr(configure_ip, "configure_device_ip", rec)
    ConfigurarController(shared).apply_ip("PC1", "10.0.0.2", "255.255.255.0", "10.0.0.1",
                                          dry_run=False)
    assert rec.calls == []
    w = shared.assistant.pending
    assert w.group == "ip"
    assert w.instruction == "Abre la ventana de IP de una PC en la pestaña Desktop."
    text = "\n".join(logs(shared))
    assert "No se movió nada" in text and "desktop_tab" not in text


def test_aplicar_ip_dry_run_no_necesita_calibracion(shared, registry, monkeypatch):  # noqa: F811
    rec = Recorder(shared)
    monkeypatch.setattr(configure_ip, "configure_device_ip", rec)
    ConfigurarController(shared).apply_ip("PC1", "10.0.0.2", "255.255.255.0", "10.0.0.1")
    assert len(rec.calls) == 1 and shared.assistant.pending is None


def test_aplicar_ip_a_todas_real_sin_calibrar_tambien_pide_asistente(shared, registry,  # noqa: F811
                                                                     monkeypatch):
    rec = Recorder(shared)
    monkeypatch.setattr(configure_ip, "configure_device_ip", rec)
    assert ConfigurarController(shared).apply_all_ips(dry_run=False) is False
    assert rec.calls == [] and shared.assistant.pending.group == "ip"


def test_ventana_ya_abierta_solo_exige_los_tres_campos(shared, registry):  # noqa: F811
    write(paths.IP_CONFIG_COORDS_PATH, {k: IP_COORDS[k] for k in
                                        ("ipv4_address", "subnet_mask", "default_gateway")})
    a = shared.assistant
    assert a.ensure("ip", [k for k, _ in configure_ip.FIELDS]) is True
    assert a.ensure("ip") is False                        # el flujo completo exige mas


def test_continuar_calibra_solo_ese_grupo_con_cuenta_regresiva(shared, registry,  # noqa: F811
                                                               with_key, monkeypatch):
    shared.countdown = 2
    a = shared.assistant
    assert not a.ensure("ip")
    seen = []

    def auto(**kw):
        seen.append((kw, shared.runner.touches_mouse))
        write(paths.IP_CONFIG_COORDS_PATH, IP_COORDS)

    monkeypatch.setattr(calibrate, "auto_calibrate", auto)
    assert a.continuar(dry_run=False)
    (kw, mouse), = seen
    assert kw["groups"] == ["ip"] and kw["dry_run"] is False and mouse is True
    assert [e[1] for e in events(shared) if e[0] == "tick"] == [2, 1, 0]
    assert a.pending is None


def test_continuar_dry_run_solo_explica(shared, registry, monkeypatch):  # noqa: F811
    a = shared.assistant
    a.ensure("ip")
    auto = Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", auto)
    a.continuar()                                          # dry_run=True por defecto
    assert auto.calls == [] and a.pending is not None
    assert "Dry-run" in "\n".join(logs(shared))


def test_continuar_sin_nada_pendiente_o_sin_clave_avisa(shared, registry):  # noqa: F811
    a = shared.assistant
    with pytest.raises(PTError, match="pendiente"):
        a.continuar(dry_run=False)
    a.ensure("ip")
    with pytest.raises(PTError, match="clave de la IA"):
        a.continuar(dry_run=False)


def test_la_ventana_ip_se_pide_en_dos_pasos(shared, registry, with_key, monkeypatch):  # noqa: F811
    a = shared.assistant
    a.ensure("ip")
    first = a.pending.instruction
    # primera pasada (Desktop): quedan solo los puntos de la pestana IP Configuration
    monkeypatch.setattr(calibrate, "auto_calibrate", lambda **kw: write(
        paths.IP_CONFIG_COORDS_PATH,
        {k: IP_COORDS[k] for k in ("desktop_tab", "ip_configuration_item", "close_button")}))
    a.continuar(dry_run=False)
    assert a.pending is not None and a.pending.instruction != first
    assert "IP Configuration" in a.pending.instruction and "Static" in a.pending.instruction
    assert "Todavía falta" in "\n".join(logs(shared))


def test_cable_pide_el_rayo_y_se_resuelve_con_cable_coords(shared, isolated_data_dir):
    a = shared.assistant
    assert a.ensure("cable") is False
    assert a.pending.group == "cable" and a.pending.missing
    assert "search_field" not in a.pending.text and "cable_icon" not in a.pending.text
    write(paths.CABLE_COORDS_PATH, CABLE_COORDS)
    assert a.ensure("cable") is True and a.pending is None


def test_grupo_sin_asistente():
    with pytest.raises(ValueError):
        AsistenteController(Shared()).ensure("main")
