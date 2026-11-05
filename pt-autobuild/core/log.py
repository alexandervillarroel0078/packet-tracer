"""
core.log - salida de mensajes desacoplada de la consola.

core/ no usa print(): llama a emit(msg). Quien lo use registra el destino con
set_sink(fn) (el panel o un archivo de log).
Sin destino registrado los mensajes se descartan.
"""

_sink = None


def set_sink(fn):
    """Registra la funcion que recibe cada mensaje (str). None = descartar."""
    global _sink
    _sink = fn


class capture:
    """Context manager: redirige temporalmente los mensajes a `fn` y restaura el anterior."""

    def __init__(self, fn):
        self._fn = fn
        self._prev = None

    def __enter__(self):
        global _sink
        self._prev = _sink
        _sink = self._fn
        return self

    def __exit__(self, *exc):
        global _sink
        _sink = self._prev
        return False


# =====================================================================================
# Eventos estructurados: UNA sola fuente para el log, la barra de accion y el overlay.
#
# emit(msg) sigue siendo el mensaje de texto de siempre (kind="log"). emit(texto, kind=...,
# point=..., name=...) ademas describe una accion (clic, tecla, espera, verificacion...).
# Los eventos NO se escriben en el sink de texto (el log clasico no cambia): los reciben los
# "listeners" (la barra, el overlay y el log del modo visible). Sin core/ ni automation/
# dependiendo de tkinter: quien dibuja es el panel.
# =====================================================================================
import time as _time
from dataclasses import dataclass, field

KINDS = ("log", "step", "click", "type", "key", "wait", "drag", "verify", "ai", "clear",
         "confirm")

_listeners = []


@dataclass
class Event:
    kind: str
    text: str = ""
    point: tuple = None       # (x, y) destino / origen
    point2: tuple = None      # (x, y) destino de un arrastre
    name: str = None          # nombre del punto (search_field, filtered_result...)
    duration: float = None    # duracion prevista (s)
    elapsed: float = None     # duracion real, solo en el evento de cierre de una fase
    data: dict = field(default_factory=dict)   # ok, confidence, rect, step, total, ...
    t: float = field(default_factory=_time.time)


def add_listener(fn):
    """Registra fn(Event). Devuelve fn (para quitarlo con remove_listener)."""
    if fn not in _listeners:
        _listeners.append(fn)
    return fn


def remove_listener(fn):
    if fn in _listeners:
        _listeners.remove(fn)


class listen:
    """Context manager: recibe los eventos mientras dure el bloque."""

    def __init__(self, fn):
        self._fn = fn

    def __enter__(self):
        add_listener(self._fn)
        return self

    def __exit__(self, *exc):
        remove_listener(self._fn)
        return False


def emit(msg="", kind="log", *, point=None, point2=None, name=None, duration=None,
         elapsed=None, **data):
    """
    Unica funcion de salida. kind="log": mensaje de texto al sink. Otros kinds: evento de
    accion para los listeners. Todos los kinds llegan a los listeners como Event.
    """
    text = str(msg)
    if kind == "log" and _sink is not None:
        _sink(text)
    if _listeners:
        ev = Event(kind, text, tuple(point) if point is not None else None,
                   tuple(point2) if point2 is not None else None, name, duration, elapsed, data)
        for fn in list(_listeners):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001 - un listener de UI nunca rompe la accion
                pass
