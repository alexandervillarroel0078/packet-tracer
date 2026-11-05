"""
core.hands - las "manos": TODO clic, tecla, arrastre y espera de la automatizacion pasa por aqui.

Cada accion emite un evento (core.log.emit con kind/texto/punto) que usan la barra de accion,
el overlay y el log del Modo visible. Sin tkinter. Con el Modo visible apagado se comporta
exactamente como llamar a pyautogui directamente (mismo clic, mismas pausas).

Modo visible (core.visual.state):
    - moveTo con duration + pausa corta antes de cada clic, y marca del destino ~0.5 s antes;
    - paso a paso: espera "Siguiente" antes de cada clic; pausa/continuar;
    - simulate: muestra los destinos pero NO mueve el mouse real ni hace clics.
Velocidad: state.speed escala todas las pausas y duraciones (incluida la escritura).
Detener (state.cancel) corta incluso una espera; el failsafe de pyautogui sigue activo.
"""

import time
from contextlib import contextmanager

from core.log import emit
from core.visual import state

_sleep = time.sleep          # punto de enganche para pruebas

NAMES = {
    "search_field": "el buscador", "filtered_result": "el primer resultado",
    "canvas": "el lienzo", "canvas_top_left": "el lienzo", "canvas_bottom_right": "el lienzo",
}
KEYS = {"enter": "Enter", "esc": "Esc", "escape": "Esc", "delete": "Supr", "ctrl": "Ctrl",
        "shift": "Shift", "alt": "Alt", "tab": "Tab", "backspace": "Retroceso"}


def _pg():
    from core import dpi_aware  # noqa: F401  la DPI awareness se fija ANTES de importar pyautogui
    import pyautogui
    return pyautogui


def pretty_key(key):
    k = str(key)
    return KEYS.get(k.lower(), k.upper() if len(k) == 1 else k.capitalize())


def pretty_keys(keys):
    return "+".join(pretty_key(k) for k in keys)


def friendly(name):
    return NAMES.get(name, name.replace("_", " ") if name else "")


def _failsafe_check():
    """Con la simulacion no se llama a pyautogui: se comprueba el failsafe a mano."""
    _pg().failSafeCheck()


# ----- esperas ----------------------------------------------------------------------------
def pause_for(seconds):
    """Duerme `seconds` (YA escalados) en trozos, atendiendo Detener y Pausa."""
    remaining = max(0.0, float(seconds))
    state.wait_gate(sleep=_sleep)
    while remaining > 0:
        chunk = min(0.1, remaining)
        _sleep(chunk)
        remaining -= chunk
        state.wait_gate(sleep=_sleep)


@contextmanager
def phase(kind, text, **kw):
    """Fase con duracion: emite el inicio y, al terminar, el mismo evento con `elapsed`."""
    t0 = time.perf_counter()
    emit(text, kind, **kw)
    try:
        yield
    finally:
        emit(text, kind, elapsed=time.perf_counter() - t0, **kw)


def wait(seconds, text=None):
    """Pausa escalada por la velocidad, visible como 'Esperando ...'."""
    real = state.scale(seconds)
    label = text or "Esperando"
    with phase("wait", f"{label} ({real:.1f} s)", duration=real):
        pause_for(real)
    return real


def sleep(seconds):
    """Pausa silenciosa (sin evento) escalada por la velocidad: para esperas internas."""
    pause_for(state.scale(seconds))


def step(n, total, text):
    emit(f"Paso {n}/{total}: {text}", "step", step=n, total=total, label=text)


def clear():
    """Quita las marcas del overlay (antes de capturar la pantalla)."""
    emit("", "clear")
    if state.visible:
        _sleep(0.12)         # tiempo para que la interfaz las borre


# ----- mouse -------------------------------------------------------------------------------
def _preview(kind, text, point, name, point2=None):
    """Marca el destino y espera (solo modo visible). Luego quita la marca."""
    if not state.visible:
        return
    secs = state.scale(state.preview)
    emit(text, kind, point=point, point2=point2, name=name, duration=secs, preview=True)
    pause_for(secs)
    clear()


def _approach(x, y):
    """Modo visible real: desplaza el mouse con duration y pausa corta antes de actuar."""
    _pg().moveTo(x, y, duration=state.scale(state.move_duration))
    pause_for(state.scale(state.click_pause))


def click(x, y, name=None, *, double=False, text=None):
    x, y = int(x), int(y)
    verb = "Doble clic" if double else "Clic"
    label = text or (f"{verb} en {friendly(name)}" if name else f"{verb} en ({x}, {y})")
    with phase("click", label, point=(x, y), name=name):
        state.wait_gate(step=True, sleep=_sleep)
        _preview("click", label, (x, y), name)
        if state.simulate:
            _failsafe_check()
            if state.visible:
                pause_for(state.scale(state.click_pause))
            return
        if state.visible:
            _approach(x, y)
        (_pg().doubleClick if double else _pg().click)(x, y)


def move_to(x, y, name=None, text=None):
    x, y = int(x), int(y)
    label = text or (f"Moviendo a {friendly(name)}" if name else f"Moviendo a ({x}, {y})")
    with phase("click", label, point=(x, y), name=name):
        if state.simulate:
            _failsafe_check()
            return
        if state.visible:
            _pg().moveTo(x, y, duration=state.scale(state.move_duration))
        else:
            _pg().moveTo(x, y)


def park():
    """Mouse a un sitio neutro (centro de la pantalla)."""
    if state.simulate:
        return
    w, h = _pg().size()
    _pg().moveTo(w // 2, h // 2)


def drag(src, dst, *, duration=0.5, pause=0.4, name=None):
    """Arrastra de src a dst (mouse pulsado). Con simulate solo dibuja la linea."""
    sx, sy, dx, dy = int(src[0]), int(src[1]), int(dst[0]), int(dst[1])
    label = "Arrastrando al lienzo" if name is None else f"Arrastrando {name}"
    with phase("drag", label, point=(sx, sy), point2=(dx, dy), name=name):
        state.wait_gate(step=True, sleep=_sleep)
        _preview("drag", label, (sx, sy), name, point2=(dx, dy))
        if state.simulate:
            _failsafe_check()
            if state.visible:
                pause_for(state.scale(state.move_duration))
            return
        pg = _pg()
        if state.visible:
            pg.moveTo(sx, sy, duration=state.scale(state.move_duration))
        else:
            pg.moveTo(sx, sy)
        pause_for(state.scale(pause))
        pg.mouseDown()
        try:
            pause_for(state.scale(pause))
            pg.moveTo(dx, dy, duration=state.scale(max(0.0, duration)))
            pause_for(state.scale(pause))
        finally:
            try:
                pg.mouseUp()          # nunca dejar el boton pulsado
            except Exception:  # noqa: BLE001
                pass
        pause_for(state.scale(pause))


# ----- teclado -----------------------------------------------------------------------------
def type_text(text, interval=0.05):
    text = str(text)
    with phase("type", f"Escribiendo: {text}", typed=text):
        if state.simulate:
            _failsafe_check()
            if state.visible:
                pause_for(state.scale(min(1.0, 0.04 * len(text))))
            return
        _pg().write(text, interval=state.scale(max(0.0, interval)))


def press(key):
    with phase("key", f"Tecla: {pretty_key(key)}", keys=(str(key),)):
        if state.simulate:
            _failsafe_check()
            return
        _pg().press(key)


def hotkey(*keys):
    with phase("key", f"Tecla: {pretty_keys(keys)}", keys=tuple(keys)):
        if state.simulate:
            _failsafe_check()
            return
        _pg().hotkey(*keys)


# ----- verificacion ------------------------------------------------------------------------
def verify_result(name, ok, confidence, rect=None, point=None):
    """
    Resalta el recorte buscado: verde si coincide, rojo si no, con el % de confianza.
    rect = [l, t, w, h] en unidades de pantalla. Solo espera en modo visible.
    """
    text = f"Verificando punto: {'OK' if ok else 'NO'} {confidence:.2f}"
    emit(text, "verify", point=point, name=name, duration=state.scale(state.preview),
         ok=bool(ok), confidence=float(confidence), rect=list(rect) if rect else None)
    if state.visible:
        pause_for(state.scale(state.preview))
        clear()
