"""
automation.common - piezas compartidas por los modulos de automation/.

Convenciones de TODAS las funciones publicas de automation/:
    - dry_run=True por defecto: calculan y muestran el plan sin tocar mouse ni teclado.
    - log: callback que recibe cada mensaje (def. core.log.emit); nunca print().
    - cancel: threading.Event opcional; si se activa, la accion se detiene (CancelledError).
    - errores esperables -> excepciones de core.errors (PTError); nunca sys.exit() / input().
"""

import time

from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
from core.errors import CancelledError, PTError
from core.log import emit


def get_log(log):
    return log if log is not None else emit


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise CancelledError("accion cancelada por el usuario")


def pyautogui_ready():
    """Importa pyautogui con un mensaje claro si falta y activa el failsafe."""
    try:
        import pyautogui
    except ImportError as e:
        raise PTError("falta pyautogui. Instala:  pip install -r requirements.txt") from e
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    return pyautogui


def dpi_header(log):
    ok, msg = dpi_aware.verify()
    log(f"  DPI awareness: {dpi_aware.STATUS}")
    log(f"  {'' if ok else '[!] '}{msg}")


def countdown(seconds, log=None, cancel=None, text="Empezando en {i}...  (enfoca Packet Tracer)"):
    """Cuenta regresiva visible (un mensaje por segundo). CancelledError si se cancela."""
    log = get_log(log)
    for i in range(max(0, int(seconds)), 0, -1):
        check_cancel(cancel)
        log("  " + text.format(i=i))
        time.sleep(1)
    check_cancel(cancel)


def run_guarded(fn, log=None):
    """
    Ejecuta fn() traduciendo el failsafe de pyautogui y Ctrl+C en CancelledError, para que
    el llamador (panel) los muestre como "detenido" y no como un fallo.
    """
    import pyautogui
    try:
        return fn()
    except pyautogui.FailSafeException as e:
        raise CancelledError("ABORTADO por failsafe (mouse en la esquina superior izquierda)") from e
    except KeyboardInterrupt as e:
        raise CancelledError("interrumpido por el usuario") from e
