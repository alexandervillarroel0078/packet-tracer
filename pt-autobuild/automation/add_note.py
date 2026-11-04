"""
add_note.py - Escribe una NOTA de texto en el lienzo de Cisco Packet Tracer.

Packet Tracer tiene un atajo oficial para la herramienta de notas: la tecla
"N" activa "Place Note Mode" directamente. Por eso este script NO necesita
calibrar ni hacer clic en ningun icono (no usa data/note_coords.json).

Reutiliza core/:
    dpi_aware   marca el proceso DPI-aware (antes que pyautogui)
    canvas      limites del lienzo calibrado (in_box / random_in_box)
    ptwindow    click_point / park_mouse

Uso (como funcion; el panel usa la misma secuencia dentro de build_topology):
    add_note("10.0.0.0/24", 300, 250)                        # posicion exacta (dry-run)
    add_note("LAN de gestion", random_pos=True)              # posicion aleatoria
    add_note("texto", 300, 250, dry_run=False)               # escribe de verdad

dry_run=True es el valor por defecto: solo muestra el plan. La posicion es X Y (enteros, pixeles
de pantalla) O random_pos=True (aleatoria dentro del canvas calibrado, con margen).

Secuencia (confirmada a mano en Packet Tracer):
    cuenta regresiva -> clic de foco en (X, Y) -> tecla 'n' (Place Note Mode)
    -> clic en (X, Y) -> escribir el texto -> Escape (Escape SOLO guarda la
    nota; el clic previo en "zona vacia" la cancelaba).
    El clic de foco hace falta al encadenar notas: tras el Escape anterior el
    foco sale de la ventana de Packet Tracer y la 'n' siguiente se perderia.

Seguridad: failsafe de pyautogui (mouse a la esquina superior izquierda =
aborta), pausa configurable entre pasos.
"""

import time

from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui
from core import canvas

import pyautogui

from core import ptwindow  # noqa: E402
from core.errors import PTError
from automation import common

DEFAULT_MARGIN = 30  # px de separacion con los bordes para la posicion aleatoria


def place_note(text, x, y, *, pause=0.4, tool_delay=0.4, type_interval=0.03,
               focus_xy=None):
    """Escribe UNA nota en (x, y). Unica fuente de la secuencia de notas.

    Flujo confirmado a mano en Packet Tracer:
        [clic de foco] -> tecla 'n' (Place Note Mode) -> clic en (x, y)
        -> escribir el texto -> Escape   (Escape SOLO: guarda la nota)

    focus_xy: si se pasa, se hace clic ahi ANTES de 'n' para recuperar el
    foco de la VENTANA de Packet Tracer. Hace falta al encadenar notas: tras
    el Escape de la nota anterior el foco sale de la ventana y la 'n'
    siguiente se perderia.

    IMPORTANTE al encadenar varias notas: focus_xy debe ser un punto FIJO y
    vacio del lienzo (ej. una esquina), NO la posicion de la propia nota (ni
    de la nota anterior/siguiente). Si dos notas quedan cerca, el cuadro de
    texto de la anterior puede seguir abierto y tapar esa coordenada; el
    clic de foco caeria DENTRO de ese cuadro en vez de en lienzo vacio, y la
    'n' se escribiria como caracter literal dentro de la nota anterior en
    vez de activar Place Note Mode (bug real ya visto: notas encadenadas
    dentro de un mismo cuadro de texto). Ver note_focus_xy en build.py.

    Asume que pyautogui.FAILSAFE lo gestiona el llamador. No hace cuenta
    regresiva. Propaga FailSafeException / KeyboardInterrupt.
    """
    if focus_xy is not None:
        ptwindow.click_point((int(focus_xy[0]), int(focus_xy[1])), pause)
    pyautogui.press("n")
    time.sleep(tool_delay)
    ptwindow.click_point((int(x), int(y)), pause)
    pyautogui.typewrite(str(text), interval=max(0.0, type_interval))
    time.sleep(pause)
    pyautogui.press("esc")                               # Escape solo: guarda
    time.sleep(pause)


def add_note(text, x=None, y=None, *, random_pos=False, margin=DEFAULT_MARGIN,
             dry_run=True, pause=0.4, tool_delay=0.4, type_interval=0.03, countdown=5,
             log=None, cancel=None):
    """
    Escribe una nota en el lienzo (posicion exacta X Y, o aleatoria con random_pos=True).
    dry_run=True (por defecto) solo muestra el plan. Devuelve (x, y) de la nota.
    Lanza PTError si falta el texto/posicion o queda fuera del canvas, y CancelledError si
    se cancela o salta el failsafe.
    """
    log = common.get_log(log)
    log("=" * 64)
    log("  Nota en el lienzo")
    log("=" * 64)
    common.dpi_header(log)

    if not text:
        raise PTError("indica el TEXTO de la nota.")
    has_xy = x is not None or y is not None
    if random_pos and has_xy:
        raise PTError("usa posicion aleatoria O coordenadas X Y, no ambos.")
    if not random_pos and not has_xy:
        raise PTError("indica la posicion de la nota: X Y o aleatoria.")
    if not random_pos and (x is None or y is None):
        raise PTError("faltan coordenadas: se necesitan X e Y (o usa posicion aleatoria).")

    box = canvas.load_box()
    x0, y0, x1, y1 = box
    log(f"  Canvas calibrado: ({x0}, {y0}) -> ({x1}, {y1})")

    if random_pos:
        nx, ny = canvas.random_in_box(box, margin)
        log(f"  Posicion aleatoria (margen {margin}px): ({nx}, {ny})")
    else:
        nx, ny = int(x), int(y)

    if not canvas.in_box(nx, ny, box):
        raise PTError(f"({nx}, {ny}) queda FUERA del canvas calibrado "
                      f"(X valido: {x0}..{x1}   Y valido: {y0}..{y1}). No se ejecuta nada.")

    if not str(text).isascii():
        log("  [!] Aviso: pyautogui.typewrite solo escribe ASCII con fiabilidad; "
            "los acentos/enes pueden salir mal.")
    log(f'  Nota: "{text}"  en ({nx}, {ny})')

    if dry_run:
        log("-" * 64)
        log("  Plan:")
        log(f"    1. cuenta regresiva {countdown}s")
        log(f"    2. clic de foco en ({nx}, {ny})  (recupera el foco de la ventana)")
        log("    3. tecla 'n'  (activa Place Note Mode)")
        log(f"    4. clic en el lienzo ({nx}, {ny})")
        log(f'    5. escribir "{text}"  (interval {type_interval}s)')
        log("    6. Escape  (guarda la nota; sin clic previo en zona vacia)")
        log("")
        log("  DRY-RUN: no se movera el mouse.")
        return nx, ny

    common.pyautogui_ready()
    common.countdown(countdown, log, cancel)
    common.check_cancel(cancel)

    def go():
        place_note(text, nx, ny, pause=pause, tool_delay=tool_delay,
                   type_interval=type_interval, focus_xy=(nx, ny))
        ptwindow.park_mouse()

    common.run_guarded(go)
    log(f'  Nota "{text}" colocada en ({nx}, {ny}).')
    return nx, ny
