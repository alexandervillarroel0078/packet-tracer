"""
Prueba de humo del panel: crea la ventana, carga las 4 pestanas, comprueba el modo seguro por
defecto y la cierra. pyautogui esta bloqueado (conftest): ningun clic puede salir de aqui.
"""

import os

import pytest

tk = pytest.importorskip("tkinter")

from core import paths  # noqa: E402
from panel.controllers.runner import ActionRunner  # noqa: E402
from panel.main import ADVANCED_TABS, TABS, PanelApp  # noqa: E402


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
    assert names == list(TABS) == ["Simple", "Avanzado", "Ajustes"]
    sub = [app.adv_nb.tab(i, "text") for i in range(app.adv_nb.index("end"))]
    assert sub == list(ADVANCED_TABS) == ["Colocar", "Configurar", "Calibracion"]
    assert set(app.views) == set(TABS) - {"Avanzado"} | set(ADVANCED_TABS)
    assert app.nb.tab(app.nb.select(), "text") == "Simple"       # modo simple por defecto


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
    assert c.groups() == ["main"]                  # cable e ip ya no tienen selector
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


def test_ajustes_selector_de_proveedor_guarda_y_conserva_cada_clave(app, monkeypatch):
    from core import paths, settings
    a = app.views["Ajustes"]
    assert a.selected() == "openai"                              # por defecto
    assert "OPENAI_API_KEY" in a.key_label.cget("text")
    a.key_var.set("sk-proj-clave-openai-1111")
    a.model_var.set("modelo-vision-x")
    a.provider_var.set("Anthropic")
    a._on_provider()                                             # cambia de proveedor
    assert a.selected() == "anthropic" and "ANTHROPIC_API_KEY" in a.key_label.cget("text")
    assert a.key_var.get() == "" and a.model_var.get() == "claude-sonnet-5-5"
    a.key_var.set("sk-ant-api03-clave-anthropic-2222")
    app.guard(a._save)()                                         # guarda el proveedor mostrado
    a.provider_var.set("OpenAI")
    a._on_provider()
    assert a.key_var.get() == "sk-proj-clave-openai-1111"        # no se perdio lo escrito
    app.guard(a._save)()
    s = settings.read_settings()
    assert s["provider"] == "openai"
    assert s["providers"]["anthropic"]["api_key"] == "sk-ant-api03-clave-anthropic-2222"
    assert s["providers"]["openai"]["model"] == "modelo-vision-x"
    log = log_text(app)
    assert "OpenAI" in log and "Anthropic" in log
    assert "clave-openai-1111" not in log and "clave-anthropic-2222" not in log
    assert os.path.exists(paths.ENV_PATH)


def test_simple_ejemplo_gris_dry_run_y_estado(app):
    s = app.views["Simple"]
    assert s.dry_var.get() is True and s.btn_build.real is False
    assert s.btn_build.cget("text") == "Construir"
    assert s.get_text() == "" and "1 switch, 1 PC" in s.text.get("1.0", "end")   # ejemplo, no valor
    s._hide_placeholder()
    s.text.insert("1.0", "2 routers")
    assert s.get_text() == "2 routers"
    s.dry_var.set(False)
    assert s.btn_build.real is True
    assert "Calibración:" in app.calib_label.cget("text") and "API:" in app.api_label.cget("text")
    # un unico boton de calibracion en Simple, que sigue el modo Dry-run
    assert s.btn_cal.real is True and s.btn_cal.cget("text") == "Calibrar (mueve el mouse)"
    s.dry_var.set(True)
    assert s.btn_cal.real is False and s.btn_cal.cget("text") == "Calibrar"
    assert not hasattr(app, "btn_autocal")


def test_simple_construir_sin_calibrar_dry_run_explica_en_lenguaje_simple(app):
    s = app.views["Simple"]
    s._hide_placeholder()
    s.text.insert("1.0", "1 switch, 1 PC")
    app.guard(s._build)()
    pump(app)
    text = log_text(app)
    assert "Voy a calibrar" in text and "search_field" not in text


def _all_buttons(widget):
    out = []
    for w in widget.winfo_children():
        if w.winfo_class() in ("Button", "TButton"):
            out.append(w)
        out += _all_buttons(w)
    return out


def test_simple_solo_tiene_un_boton_de_calibracion(app):
    s = app.views["Simple"]
    texts = [b.cget("text") for b in _all_buttons(s.btn_build.master)]
    # un solo boton que calibra; el otro solo muestra la ultima captura (no actua)
    assert [t for t in texts if "alibr" in t] == ["Calibrar", "Ver última calibración"]


def test_calibracion_solo_muestra_calibrar_y_el_resto_esta_plegado(app):
    c = app.views["Calibracion"]
    assert c.debug.opened is False and c.debug.body.winfo_manager() == ""
    assert c.btn_cal.cget("text") == "Calibrar" and c.dry_var.get() is True
    assert c.summary.cget("text").startswith("Falta calibrar")
    # lo de depuracion vive dentro de la seccion plegable
    for w in (c.btn_show, c.btn_force, c.btn_verify, c.tree, c.btn_cap, c.btn_ov_cal):
        assert str(w).startswith(str(c.debug.body))
    assert not hasattr(c, "group_vars") and not hasattr(c, "btn_auto")
    c.debug.toggle()
    assert c.debug.opened and c.debug.body.winfo_manager() == "pack"
    assert "Herramientas de depuración" in c.debug.toggle_btn.cget("text")


def test_asistente_aparece_al_faltar_calibracion_y_continuar_respeta_el_dry_run(app):
    import json
    os.makedirs(os.path.dirname(paths.TOPOLOGY_ACTUAL_PATH), exist_ok=True)
    with open(paths.TOPOLOGY_ACTUAL_PATH, "w", encoding="utf-8") as f:
        json.dump({"dispositivos": [{"id": 1, "tipo": "end_device", "modelo": "PC",
                                     "nombre": "PC1", "posicion": [500, 400]}]}, f)
    cfg = app.views["Configurar"]
    cfg.refresh_devices()
    cfg.pc_var.set("PC1")
    cfg.ip_var.set("10.0.0.2")
    cfg.mask_var.set("255.255.255.0")
    cfg.gw_var.set("10.0.0.1")
    assert not app.wizard.visible
    cfg.dry_var.set(False)
    app.guard(cfg._ip)()
    pump(app)
    assert app.wizard.visible
    assert "Desktop" in app.wizard.body.cget("text") and "desktop_tab" not in app.wizard.body.cget("text")
    cfg.dry_var.set(True)                       # Continuar en dry-run: solo explica
    app.guard(app.wizard._continue)()
    pump(app)
    assert "Dry-run" in log_text(app) and app.wizard.visible
    app.wizard._cancel()
    assert not app.wizard.visible


def test_modo_visible_desmarcado_por_defecto_y_sin_ventanas(app):
    s = app.views["Simple"]
    assert s.visible_var.get() is False
    assert app.shared.visual.visible is False and app.visible_view.active is False


def test_modo_visible_crea_la_barra_y_el_overlay_y_los_cierra(app):
    s = app.views["Simple"]
    s.visible_var.set(True)
    s._on_visible()
    assert app.visible_view.active and app.shared.visual.visible is True
    from core.log import Event
    line = app.visible_view.on_event(Event("click", "Clic en el buscador", elapsed=0.5))
    assert "Clic en el buscador" in line
    app.visible_view.on_event(Event("click", "Clic en el buscador", point=(10, 10),
                                    name="search_field", duration=0.5, data={"preview": True}))
    app.visible_view.tick()
    s._toggle_pause()
    assert s.pause_btn.cget("text") == "Continuar"
    s._on_speed(2)
    assert app.shared.visual.state.speed == 2.0
    s.visible_var.set(False)
    s._on_visible()
    assert not app.visible_view.active and app.shared.visual.state.paused is False
    assert s.pause_btn.cget("text") == "Pausa"
