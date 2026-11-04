"""
core.log - salida de mensajes desacoplada de la consola.

core/ no usa print(): llama a emit(msg). Quien lo use registra el destino con
set_sink(fn) (el panel, un archivo de log, o print en una consola de pruebas).
Sin destino registrado los mensajes se descartan.
"""

_sink = None


def set_sink(fn):
    """Registra la funcion que recibe cada mensaje (str). None = descartar."""
    global _sink
    _sink = fn


def emit(msg=""):
    if _sink is not None:
        _sink(str(msg))
