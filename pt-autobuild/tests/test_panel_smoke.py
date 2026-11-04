"""
Prueba de humo del panel: crea la ventana, carga las 4 pestanas, comprueba el modo seguro por
defecto y la cierra. pyautogui esta bloqueado (conftest): ningun clic puede salir de aqui.
"""

import os

import pytest

tk = pytest.importorskip("tkinter")

from core import paths  # noqa: E402
from panel.controllers.runner import ActionRunner  # noqa: E402
from panel.main import TABS, PanelApp  # noqa: E402


@pytest.fixture(scope="module")
def tk_root():
    """Un unico Tk por modulo: crear/destruir varios en un mismo proceso rompe la busqueda de
    la libreria Tcl en algunas instalaciones de Windows."""
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no hay display para tkinter: {e}")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def app(tk_root):
    window = tk.Toplevel(tk_root)
    window.withdraw()
    application = PanelApp(window, runner=ActionRunner(sync=True, tick_seconds=0))
    window.update_idletasks()
    yield application
    try:
        application.close()
    except tk.TclError:
        pass


def pump(app):
    for ev in app.runner.drain():
        app._handle(ev)


def log_text(app):
    return app.log.text.get("1.0", "end")


def test_carga_las_cuatro_pestanas(app):
    names = [app.nb.tab(i, "text") for i in range(app.nb.index("end"))]
    assert names == list(TABS) == ["Colocar", "Configurar", "Calibracion", "Ajustes"]
    assert set(app.views) == set(TABS)


def test_modo_seguro_por_defecto(app):
    colocar, configurar = app.views["Colocar"], app.views["Configurar"]
    assert colocar.dry_var.get() is True and configurar.dry_var.get() is True
    for btn in (colocar.btn_build, colocar.btn_move, configurar.btn_ip, configurar.btn_ip_all,
                configurar.btn_host):
        assert btn.real is False
        assert "dry-run" in btn.cget("text").lower()
    # se ve CLARAMENTE cuando va a actuar de verdad: otro texto y otro color
    colocar.dry_var.set(False)
    configurar.dry_var.set(False)
    for btn in (colocar.btn_build, colocar.btn_move, configurar.btn_ip, configurar.btn_ip_all,
                configurar.btn_host):
        assert btn.real is True
        assert "mueve el mouse" in btn.cget("text").lower() or "mouse" in btn.cget("text").lower()
        assert btn.cget("bg") == "#b71c1c"
    colocar.dry_var.set(True)
    assert colocar.btn_build.cget("bg") == "#2e7d32"


def test_colocar_cargar_ejemplo_y_vista_previa(app):
    v = app.views["Colocar"]
    v.example_var.set("redes.txt")
    v._example()
    assert "SWITCHES" in v.get_text()
    v._preview()                                   # sin calibrar: error claro, no excepcion
    out = v.out.get("1.0", "end")
    assert "ERROR" in out and "Calibra" in out
    assert "[ERROR]" in log_text(app)
    assert "Traceback" not in log_text(app)


def test_construir_real_sin_calibrar_no_actua_y_ofrece_recalibrar(app):
    v = app.views["Colocar"]
    v.set_text("2 routers, 1 switch")
    v.dry_var.set(False)
    app.guard(v._build)()
    pump(app)
    assert "No se construyo" in log_text(app)
    assert str(v.btn_recal.cget("state")) == "normal"          # "Recalibrar y continuar"
    assert "search_field" in v.out.get("1.0", "end")
    assert not app.runner.busy


def test_construir_dry_run_con_calibracion(app):
    import json
    os.makedirs(paths.DATA_DIR, exist_ok=True)
    with open(paths.COORDS_PATH, "w", encoding="utf-8") as f:
        json.dump({"search_field": [300, 1000], "filtered_result": [200, 950],
                   "canvas": {"top_left": [12, 150], "bottom_right": [1800, 800]}}, f)
    v = app.views["Colocar"]
    v.set_text("2 routers, 2 switches, 4 PC")
    v._preview()
    assert "DRY-RUN" in v.out.get("1.0", "end")
    app.guard(v._build)()                          # dry-run marcado: no mueve nada
    pump(app)
    assert "DRY-RUN" in log_text(app)


def test_configurar_generar_y_copiar(app):
    colocar, cfg = app.views["Colocar"], app.views["Configurar"]
    colocar.set_text("SWITCHES: Sw1\nROUTERS: R01\nRED Red1: 192.168.10.0/24 R01\nPC1 .2\n")
    cfg._generate()
    assert "hostname R01" in cfg.out.get("1.0", "end")
    cfg._copy()
    assert "hostname R01" in app.root.clipboard_get()


def test_configurar_error_claro_sin_topologia(app):
    cfg = app.views["Configurar"]
    app.guard(cfg._generate)()
    assert "[ERROR]" in log_text(app) and "topologia" in log_text(app)


def test_ajustes_mostrar_ocultar_y_guardar_sin_imprimir_la_key(app):
    a = app.views["Ajustes"]
    assert a.key_entry.cget("show") != ""
    a.show_var.set(True)
    a._toggle_show()
    assert a.key_entry.cget("show") == ""
    secret = "sk-ant-api03-PRUEBA-SMOKE-0000"
    a.key_var.set(secret)
    a.model_var.set("claude-sonnet-5-5")
    app.guard(a._save)()
    assert secret not in log_text(app) and "guardados" in log_text(app)
    a.key_var.set("")
    app.guard(a._save)()
    assert "[ERROR] escribe la API key" in log_text(app)
    assert "DPI awareness" in a.dpi_out.get("1.0", "end")


def test_calibracion_instrucciones_tabla_y_sin_api_key(app, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    c = app.views["Calibracion"]
    assert "buscador" in c.instr.cget("text")
    c.group_vars["cable"].set(True)
    c._refresh_instructions()
    assert "rayo" in c.instr.cget("text")
    assert len(c.tree.get_children()) == 16
    app.guard(c._show)()                           # sin API key: error claro en el panel
    assert "[ERROR] falta la API key" in log_text(app)


def test_detener_esta_deshabilitado_en_reposo_y_botones_se_bloquean_al_correr(app):
    assert str(app.status.stop.cget("state")) == "disabled"
    app.runner.state = "running"
    app._handle(("state", "running", "x"))
    assert str(app.status.stop.cget("state")) == "normal"
    assert str(app.views["Colocar"].btn_build.cget("state")) == "disabled"
    app.runner.state = "idle"
    app._handle(("state", "idle", "x"))
    assert str(app.views["Colocar"].btn_build.cget("state")) == "normal"


def test_cuenta_regresiva_visible(app):
    app._handle(("tick", 3))
    assert "Empezando en 3" in app.status.countdown.cget("text")
    assert app.status.countdown.winfo_manager() == "pack"
    app._handle(("tick", 0))
    assert app.status.countdown.winfo_manager() == ""


def test_cuenta_regresiva_del_panel_llega_al_controlador(app):
    app.countdown_var.set("7")
    assert app.shared.countdown == 7
    app.countdown_var.set("")                       # mientras se escribe no rompe
    assert app.shared.countdown == 7


def test_cerrar_destruye_la_ventana(app):
    app.close()
    with pytest.raises(tk.TclError):
        app.root.winfo_exists() and app.root.update()
        app.root.title()
