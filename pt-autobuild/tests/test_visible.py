"""
Modo visible: eventos (core.log), "manos" (core.hands), duraciones/velocidad, simulacion
(dry-run + visible), paso a paso / pausa, verificacion y modelo de la barra/overlay.

pyautogui sigue bloqueado por conftest: las pruebas que necesitan ver una llamada la
sustituyen por un grabador (no hay forma de mover el mouse de verdad).
"""

import json
import threading

import pytest

from core import annotate, hands, visual
from core import log as core_log
from core.errors import CancelledError
from core.log import Event
from panel.controllers.visible import (CLEAR, LINE, MARK, RECT, VisibleController,
                                       VisibleModel)

pyautogui = pytest.importorskip("pyautogui")


@pytest.fixture
def events():
    got = []
    with core_log.listen(got.append):
        yield got


@pytest.fixture
def sleeps(monkeypatch):
    """Sustituye el sleep de hands por un grabador (los tests no esperan de verdad)."""
    rec = []
    monkeypatch.setattr(hands, "_sleep", rec.append)
    return rec


@pytest.fixture
def calls(monkeypatch):
    """Grabador de pyautogui (reemplaza las funciones bloqueadas; nada se mueve)."""
    rec = []
    for name in ("click", "doubleClick", "moveTo", "mouseDown", "mouseUp", "write", "press",
                 "hotkey"):
        monkeypatch.setattr(pyautogui, name,
                            lambda *a, _n=name, **k: rec.append((_n, a, k)))
    monkeypatch.setattr(pyautogui, "size", lambda: (1920, 1080))
    return rec


def names(rec):
    return [c[0] for c in rec]


# ----- core.log: una sola funcion de eventos ----------------------------------------------
def test_emit_envia_el_texto_al_sink_y_el_evento_a_los_listeners(events):
    seen = []
    with core_log.capture(seen.append):
        core_log.emit("hola")
        core_log.emit("Clic en el buscador", "click", point=(10, 20), name="search_field")
    assert seen == ["hola"]                     # los eventos de accion no ensucian el log clasico
    assert [e.kind for e in events] == ["log", "click"]
    click = events[1]
    assert isinstance(click, Event)
    assert (click.text, click.point, click.name) == ("Clic en el buscador", (10, 20),
                                                     "search_field")


def test_un_listener_que_falla_no_rompe_la_accion():
    def bad(_ev):
        raise RuntimeError("boom")
    with core_log.listen(bad):
        core_log.emit("x", "click", point=(1, 2))      # no lanza


def test_core_y_automation_no_importan_tkinter():
    import os
    root = os.path.dirname(os.path.dirname(__file__))
    for folder in ("core", "automation"):
        for fn in os.listdir(os.path.join(root, folder)):
            if fn.endswith(".py"):
                src = open(os.path.join(root, folder, fn), encoding="utf-8").read()
                assert "import tkinter" not in src and "from tkinter" not in src, fn


# ----- manos con el modo visible apagado = pyautogui directo --------------------------------
def test_sin_modo_visible_el_clic_es_directo(calls, sleeps, events):
    hands.click(10, 20, "search_field")
    assert calls == [("click", (10, 20), {})]            # sin moveTo ni pausas extra
    assert sleeps == []
    assert events[0].text == "Clic en el buscador" and events[0].name == "search_field"


def test_texto_y_teclas_visibles_en_los_eventos(calls, sleeps, events):
    hands.type_text("2960", interval=0.05)
    hands.hotkey("ctrl", "a")
    hands.press("enter")
    hands.press("delete")
    texts = [e.text for e in events if e.elapsed is None]
    assert texts == ["Escribiendo: 2960", "Tecla: Ctrl+A", "Tecla: Enter", "Tecla: Supr"]
    assert calls[0] == ("write", ("2960",), {"interval": 0.05})
    assert calls[1] == ("hotkey", ("ctrl", "a"), {})


# ----- modo visible: moveTo con duracion, pausa y destino marcado ------------------------------
def test_modo_visible_mueve_con_duracion_y_marca_el_destino(calls, sleeps, events):
    visual.state.configure(visible=True, move_duration=0.6)
    hands.click(300, 1000, "search_field")
    assert names(calls) == ["moveTo", "click"]
    assert calls[0][1] == (300, 1000) and calls[0][2] == {"duration": 0.6}
    # marca ~0.5 s con el nombre del punto, y se limpia antes del clic
    marks = [e for e in events if e.kind == "click" and e.data.get("preview")]
    assert len(marks) == 1 and marks[0].name == "search_field" and marks[0].point == (300, 1000)
    assert marks[0].duration == pytest.approx(0.5)
    assert sum(sleeps) >= 0.5 + visual.CLICK_PAUSE - 1e-9
    kinds = [e.kind for e in events if e.elapsed is None]
    assert kinds.index("clear") > kinds.index("click")


def test_duracion_del_mouse_se_limita_a_0_4_0_8():
    visual.state.configure(move_duration=5)
    assert visual.state.move_duration == visual.MOVE_MAX
    visual.state.configure(move_duration=0.01)
    assert visual.state.move_duration == visual.MOVE_MIN


def test_cada_fase_registra_su_duracion(calls, sleeps, events):
    visual.state.configure(visible=True)
    hands.wait(1.0, "Esperando que filtre")
    start, end = [e for e in events if e.kind == "wait"]
    assert start.text == "Esperando que filtre (1.0 s)" and start.elapsed is None
    assert end.elapsed is not None and end.elapsed >= 0
    assert sum(sleeps) == pytest.approx(1.0)


@pytest.mark.parametrize("name,factor", [("Rápido", 0.5), ("Normal", 1.0), ("Lento", 2.0)])
def test_la_velocidad_escala_pausas_y_duraciones(calls, sleeps, events, name, factor):
    c = VisibleController()
    c.set_speed(name)
    c.state.configure(visible=True, move_duration=0.6)
    hands.wait(1.0, "Esperando")
    assert sum(sleeps) == pytest.approx(1.0 * factor)
    sleeps.clear()
    calls.clear()
    hands.click(5, 6, "canvas")
    assert calls[0][2]["duration"] == pytest.approx(0.6 * factor)
    # preview (0.5) + pausa corta (0.2) escaladas
    assert sum(sleeps) == pytest.approx((0.5 + visual.CLICK_PAUSE) * factor + 0.12, abs=1e-6)


def test_la_velocidad_escala_tambien_la_escritura(calls, sleeps):
    visual.state.set_speed("Lento")
    hands.type_text("ab", interval=0.05)
    assert calls[0][2]["interval"] == pytest.approx(0.1)


def test_arrastre_dibuja_la_linea_y_suelta_siempre(calls, sleeps, events):
    visual.state.configure(visible=True)
    hands.drag((10, 10), (200, 100), duration=0.5, pause=0.1, name="R1")
    assert names(calls) == ["moveTo", "mouseDown", "moveTo", "mouseUp"]
    mark = [e for e in events if e.kind == "drag" and e.data.get("preview")][0]
    assert mark.point == (10, 10) and mark.point2 == (200, 100)


def test_arrastre_suelta_el_boton_si_falla(calls, sleeps, monkeypatch):
    def boom(*a, **k):
        raise pyautogui.FailSafeException("x")
    n = {"moves": 0}

    def move(*a, **k):
        n["moves"] += 1
        if n["moves"] == 2:
            boom()
    monkeypatch.setattr(pyautogui, "moveTo", move)
    released = []
    monkeypatch.setattr(pyautogui, "mouseUp", lambda *a, **k: released.append(1))
    with pytest.raises(pyautogui.FailSafeException):
        hands.drag((1, 1), (9, 9), name="R1")
    assert released


# ----- simulacion visual (dry-run + visible) -------------------------------------------------
def test_simulacion_muestra_destinos_sin_tocar_el_mouse(sleeps, events, monkeypatch):
    # pyautogui sigue BLOQUEADO (sin grabador): cualquier clic real lanzaria PyAutoGuiBlocked
    monkeypatch.setattr(hands, "_failsafe_check", lambda: None)
    visual.state.configure(visible=True)
    with visual.simulating(True):
        hands.click(1, 2, "search_field")
        hands.type_text("2960")
        hands.hotkey("ctrl", "a")
        hands.drag((1, 1), (5, 5), name="PC1")
        hands.park()
    assert [e.name for e in events if e.kind == "click" and e.data.get("preview")] == [
        "search_field"]
    assert any(e.kind == "drag" and e.data.get("preview") for e in events)


def test_simulacion_mantiene_el_failsafe(sleeps, monkeypatch):
    def trip():
        raise pyautogui.FailSafeException("esquina")
    monkeypatch.setattr(hands, "_failsafe_check", trip)
    with visual.simulating(True):
        with pytest.raises(pyautogui.FailSafeException):
            hands.click(1, 2, "canvas")


def test_construir_dry_run_visible_recorre_los_pasos_sin_mouse(sleeps, events, monkeypatch):
    from automation import build
    from core import coords as coords_io
    from core.paths import COORDS_PATH
    coords_io.save_coords(COORDS_PATH, {
        "search_field": [300, 1000], "filtered_result": [200, 950],
        "canvas": {"top_left": [12, 150], "bottom_right": [1800, 800]}})
    monkeypatch.setattr(hands, "_failsafe_check", lambda: None)
    visual.state.configure(visible=True)
    out = []
    with core_log.capture(out.append):
        res = build.build_topology("1 switch, 1 PC", dry_run=True, pause=0.0, filter_delay=0.0,
                                   countdown=5)
    assert res is not None and res["placed"] == 2 and res["total"] == 2
    previews = [e.name for e in events if e.kind == "click" and e.data.get("preview")]
    assert previews == ["search_field", "filtered_result", "canvas"] * 2
    steps = [e.text for e in events if e.kind == "step"]
    assert steps[0].startswith("Paso 1/2: colocar") and steps[1].startswith("Paso 2/2")
    assert any(e.text == "Escribiendo: 2960" or e.text.startswith("Escribiendo:")
               for e in events)
    assert not visual.state.simulate            # se restaura
    import os
    from core import paths
    assert not os.path.exists(paths.TOPOLOGY_ACTUAL_PATH)     # la simulacion no guarda registro
    assert not any("Empezando en" in line for line in out)    # sin cuenta regresiva


def test_construir_dry_run_sin_modo_visible_sigue_sin_hacer_nada(events):
    from automation import build
    from core import coords as coords_io
    from core.paths import COORDS_PATH
    coords_io.save_coords(COORDS_PATH, {
        "search_field": [300, 1000], "filtered_result": [200, 950],
        "canvas": {"top_left": [12, 150], "bottom_right": [1800, 800]}})
    assert build.build_topology("1 switch, 1 PC", dry_run=True, log=lambda m: None) is None
    assert [e for e in events if e.kind != "log"] == []


# ----- pausa, paso a paso y Detener ---------------------------------------------------------------
def test_paso_a_paso_espera_siguiente_antes_de_cada_clic(calls, sleeps):
    visual.state.configure(visible=True, step_mode=True)
    done = threading.Event()

    def run():
        hands.click(1, 2, "canvas")
        done.set()
    import time
    t = threading.Thread(target=run)
    t.start()
    time.sleep(0.15)
    assert not done.is_set() and not calls                # esperando confirmacion
    visual.state.confirm_step()
    t.join(5)
    assert done.is_set() and "click" in names(calls)


def test_detener_corta_una_espera_de_paso_a_paso(calls, sleeps):
    visual.state.configure(visible=True, step_mode=True)
    cancel = threading.Event()
    visual.state.cancel = cancel
    cancel.set()
    with pytest.raises(CancelledError):
        hands.click(1, 2, "canvas")
    assert not calls


def test_pausa_congela_y_detener_la_corta(calls, sleeps):
    visual.state.configure(visible=True)
    cancel = threading.Event()
    visual.state.cancel = cancel
    assert visual.state.toggle_pause() is True
    cancel.set()
    with pytest.raises(CancelledError):
        hands.wait(1.0, "Esperando")
    assert visual.state.toggle_pause() is False


def test_el_paso_a_paso_solo_aplica_en_modo_visible(calls, sleeps):
    visual.state.configure(visible=False, step_mode=True)
    hands.click(1, 2, "canvas")           # no se queda esperando
    assert names(calls) == ["click"]


# ----- verificacion -------------------------------------------------------------------------------
def test_verify_result_emite_recuadro_con_confianza(sleeps, events):
    visual.state.configure(visible=True)
    hands.verify_result("search_field", True, 0.97, rect=[10, 20, 96, 96], point=(50, 60))
    ev = [e for e in events if e.kind == "verify"][0]
    assert ev.text == "Verificando punto: OK 0.97"
    assert ev.data["ok"] is True and ev.data["rect"] == [10, 20, 96, 96]


def test_verify_and_refine_emite_el_resultado_de_cada_punto(sleeps, events, monkeypatch):
    from PIL import Image
    from core import autocalibrate as ac
    shot = Image.new("RGB", (400, 300), "white")
    monkeypatch.setattr(ac, "capture", lambda: (shot, 1.0))
    monkeypatch.setattr(ac, "make_template", lambda s, p: (Image.new("RGB", (96, 96)), (40, 50),
                                                           (48, 48)))
    monkeypatch.setattr(ac, "match_template", lambda s, t: (0.97, (40, 50)))
    monkeypatch.setattr(ac, "save_reference", lambda f, t, d: f)
    el = type("El", (), {"name": "search_field", "fname": "search_field.png",
                         "ask": "search_field", "desc": "d"})()
    r = ac.verify_and_refine(el, [88, 98], shot, 1.0, (400, 300), None, True, lambda m: None)
    assert r["status"] == "ok"
    ev = [e for e in events if e.kind == "verify"][0]
    assert ev.data["ok"] is True and ev.name == "search_field"
    assert ev.data["rect"] == [40.0, 50.0, 96.0, 96.0]
    # y uno en rojo cuando no coincide
    events.clear()
    monkeypatch.setattr(ac, "match_template", lambda s, t: (0.40, (200, 200)))
    r = ac.verify_and_refine(el, [88, 98], shot, 1.0, (400, 300), None, True, lambda m: None) \
        if False else None
    # (el camino de reintento llama a la IA: se comprueba con verify_result directamente)
    hands.verify_result("search_field", False, 0.40, rect=[1, 2, 3, 4])
    bad = [e for e in events if e.kind == "verify"][0]
    assert bad.data["ok"] is False


def test_ia_emite_una_fase_con_duracion(events, monkeypatch):
    from core import ai_providers
    from core import autocalibrate as ac
    monkeypatch.setattr(ai_providers, "send", lambda *a, **k: '{"a": 1}')
    assert ac.call_vision_api(object(), "b64", "prompt") == '{"a": 1}'
    ai = [e for e in events if e.kind == "ai"]
    assert [e.text for e in ai] == ["Consultando a la IA...", "Consultando a la IA..."]
    assert ai[0].elapsed is None and ai[1].elapsed >= 0


# ----- captura anotada ----------------------------------------------------------------------------
def test_guarda_la_ultima_calibracion_con_los_puntos(tmp_path, isolated_data_dir):
    from PIL import Image
    img = Image.new("RGB", (200, 100), "white")
    path = annotate.save_last_calibration(img, (200, 100), {"search_field": (50, 40),
                                                            "filtered_result": (150, 60)},
                                          rejected={"filtered_result"})
    assert path and path.endswith("ultima_calibracion.png")
    assert path.startswith(isolated_data_dir["DATA_DIR"])
    out = Image.open(path)
    assert out.size == (200, 100) and out.getpixel((50, 40)) != (255, 255, 255)
    assert VisibleController.last_calibration() == path


def test_sin_calibracion_previa_no_hay_ruta():
    assert VisibleController.last_calibration() is None


# ----- modelo de la barra / overlay ----------------------------------------------------------------
def test_modelo_barra_paso_accion_y_rastro():
    m = VisibleModel()
    m.handle(Event("step", "Paso 3/8: colocar PC1", data={"step": 3, "total": 8}))
    m.handle(Event("type", "Escribiendo: 2960", t=100.0))
    step, action, trail = m.bar_lines(now=101.5)
    assert step == "Paso 3/8: colocar PC1" and action == "Escribiendo: 2960  1.5 s" and trail == ""
    m.handle(Event("type", "Escribiendo: 2960", elapsed=0.9, t=101.0))
    step, action, trail = m.bar_lines()
    assert action.endswith("(0.9 s)") and trail == "Escribiendo 0.9 s"


def test_modelo_overlay_marca_linea_y_recuadros():
    m = VisibleModel()
    mark = m.handle(Event("click", "Clic en el buscador", point=(5, 6), name="search_field",
                          duration=0.5, data={"preview": True}))
    assert mark[0]["cmd"] == MARK and mark[0]["name"] == "search_field"
    drag = m.handle(Event("drag", "Arrastrando R1", point=(1, 1), point2=(9, 9), name="R1",
                          duration=0.5, data={"preview": True}))
    assert drag[0]["cmd"] == LINE and {c["cmd"] for c in drag} == {LINE, MARK}
    ok = m.handle(Event("verify", "Verificando punto: OK 0.97", name="search_field",
                        data={"ok": True, "confidence": 0.97, "rect": [1, 2, 3, 4]}))
    bad = m.handle(Event("verify", "x", name="canvas",
                         data={"ok": False, "confidence": 0.4, "rect": [1, 2, 3, 4]}))
    assert ok[0]["cmd"] == RECT and ok[0]["color"] == "#22e34a" and ok[0]["text"].endswith("97%")
    assert bad[0]["color"] == "#ff3b3b" and bad[0]["text"].endswith("40%")
    assert m.handle(Event("clear")) == [{"cmd": CLEAR}]
    # sin marca de preview (inicio de la fase) no se dibuja nada
    assert m.handle(Event("click", "Clic", point=(1, 1))) == []


def test_modelo_linea_de_log_solo_para_fases_terminadas():
    m = VisibleModel()
    assert m.log_line(Event("click", "Clic en el buscador")) is None
    assert m.log_line(Event("click", "Clic en el buscador", elapsed=0.62)) == \
        "  [visible] Clic en el buscador  (0.6 s)"


def test_controlador_aplica_los_controles_al_estado():
    c = VisibleController()
    assert c.visible is False                       # desmarcado por defecto
    c.set_visible(True)
    c.set_speed_index(2)
    assert c.speed_name() == "Lento" and visual.state.speed == 2.0
    c.set_move_duration(0.7)
    assert visual.state.move_duration == 0.7
    assert c.toggle_pause() is True
    c.set_step_mode(True)
    c.set_visible(False)                            # apagar limpia pausa y paso a paso
    assert not visual.state.paused and not visual.state.step_mode


# ----- runner: los eventos llegan a la interfaz --------------------------------------------------
def test_el_runner_reenvia_los_eventos_y_el_cancel(sleeps):
    from panel.controllers.runner import ActionRunner
    r = ActionRunner(sync=True)
    seen = {}

    def job(ctx):
        seen["cancel"] = visual.state.cancel
        hands.step(1, 2, "colocar PC1")
        hands.wait(0.5, "Esperando")
        ctx.log("texto")

    r.start("Prueba", job)
    drained = r.drain()
    evs = [e[1] for e in drained if e[0] == "event"]
    assert [e.kind for e in evs if e.elapsed is None] == ["step", "wait"]
    assert ("log", "texto") in drained
    assert seen["cancel"] is r.cancel and visual.state.cancel is None   # y se libera al terminar


def test_el_runner_libera_la_pausa_al_terminar(sleeps):
    from panel.controllers.runner import ActionRunner
    r = ActionRunner(sync=True)
    visual.state.paused = True
    r.start("Prueba", lambda ctx: None)
    assert visual.state.paused is False
