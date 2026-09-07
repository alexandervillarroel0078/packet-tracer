"""
add_note.py - Escribe una NOTA de texto en el lienzo de Cisco Packet Tracer.

Packet Tracer tiene un atajo oficial para la herramienta de notas: la tecla
"N" activa "Place Note Mode" directamente. Por eso este script NO necesita
calibrar ni hacer clic en ningun icono (no usa data/note_coords.json).

Reutiliza core/:
    dpi_aware   marca el proceso DPI-aware (antes que pyautogui)
    canvas      limites del lienzo calibrado (in_box / random_in_box)
    ptwindow    click_point / park_mouse

Uso (desde pt-autobuild/):
    python add_note.py "10.0.0.0/24" 300 250          # posicion exacta
    python add_note.py "LAN de gestion" --random      # posicion aleatoria
    python add_note.py "texto" 300 250 --dry-run      # plan, sin tocar el mouse

Modo (obligatorio, uno de los dos, no ambos):
    X Y        posicion exacta de la nota (enteros, pixeles de pantalla)
    --random   posicion aleatoria dentro del canvas calibrado, con margen

Secuencia (confirmada a mano en Packet Tracer):
    cuenta regresiva -> clic de foco en (X, Y) -> tecla 'n' (Place Note Mode)
    -> clic en (X, Y) -> escribir el texto -> Escape (Escape SOLO guarda la
    nota; el clic previo en "zona vacia" la cancelaba).
    El clic de foco hace falta al encadenar notas: tras el Escape anterior el
    foco sale de la ventana de Packet Tracer y la 'n' siguiente se perderia.

Seguridad: failsafe de pyautogui (mouse a la esquina superior izquierda =
aborta), pausa configurable entre pasos.
"""

import argparse
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui
from core import canvas

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala las dependencias con:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

from core import ptwindow  # noqa: E402  (usa pyautogui; va despues del guard)

DEFAULT_MARGIN = 30  # px de separacion con los bordes para --random


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


def main():
    ap = argparse.ArgumentParser(
        description="Escribe una nota de texto en el lienzo de Packet Tracer.")
    ap.add_argument("text", nargs="?", default=None,
                    help='Texto de la nota, ej. "10.0.0.0/24"')
    ap.add_argument("x", nargs="?", type=int, default=None, help="X de la nota (px).")
    ap.add_argument("y", nargs="?", type=int, default=None, help="Y de la nota (px).")
    ap.add_argument("--random", action="store_true",
                    help="Posicion aleatoria dentro del canvas (en vez de X Y).")
    ap.add_argument("--margin", type=int, default=DEFAULT_MARGIN,
                    help=f"Margen con los bordes para --random (def. {DEFAULT_MARGIN}).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Imprime el plan sin mover el mouse.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre pasos (def. 0.4).")
    ap.add_argument("--tool-delay", type=float, default=0.4,
                    help="Espera tras pulsar 'n' (Place Note Mode) (def. 0.4).")
    ap.add_argument("--type-interval", type=float, default=0.03,
                    help="Segundos entre teclas al escribir (def. 0.03).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    print("=" * 64)
    print("  add_note.py :: escribir una nota en el lienzo")
    print("=" * 64)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")

    if args.text is None:
        ap.error('indica el TEXTO de la nota, ej. python add_note.py "10.0.0.0/24" 300 250')

    # --- modo: --random XOR (x, y) --------------------------------------
    has_xy = args.x is not None or args.y is not None
    if args.random and has_xy:
        ap.error("usa --random O coordenadas X Y, no ambos.")
    if not args.random and not has_xy:
        ap.error("indica la posicion de la nota: 'X Y' o '--random'.")
    if not args.random and (args.x is None or args.y is None):
        ap.error("faltan coordenadas: se necesitan X e Y (o usa --random).")

    box = canvas.load_box()
    x0, y0, x1, y1 = box
    print(f"  Canvas calibrado: ({x0}, {y0}) -> ({x1}, {y1})")

    if args.random:
        nx, ny = canvas.random_in_box(box, args.margin)
        print(f"  Posicion --random (margen {args.margin}px): ({nx}, {ny})")
    else:
        nx, ny = int(args.x), int(args.y)

    if not canvas.in_box(nx, ny, box):
        print("-" * 64)
        print(f"  ERROR: ({nx}, {ny}) queda FUERA del canvas calibrado.")
        print(f"         X valido: {x0}..{x1}   Y valido: {y0}..{y1}")
        print("  No se ejecuta nada.")
        sys.exit(1)

    if not args.text.isascii():
        print("  [!] Aviso: pyautogui.typewrite solo escribe ASCII con fiabilidad; "
              "los acentos/enes pueden salir mal.")

    print(f'  Nota: "{args.text}"  en ({nx}, {ny})')

    if args.dry_run:
        print("-" * 64)
        print("  Plan:")
        print(f"    1. cuenta regresiva {args.countdown}s")
        print(f"    2. clic de foco en ({nx}, {ny})  (recupera el foco de la ventana)")
        print("    3. tecla 'n'  (activa Place Note Mode)")
        print(f"    4. clic en el lienzo ({nx}, {ny})")
        print(f'    5. escribir "{args.text}"  (interval {args.type_interval}s)')
        print("    6. Escape  (guarda la nota; sin clic previo en zona vacia)")
        print()
        print("  DRY-RUN: no se movera el mouse.")
        print("=" * 64)
        return

    print()
    print("  Plan: clic de foco -> 'n' -> clic en el lienzo -> escribir -> Escape")
    print("  Pon el foco en Packet Tracer.")
    for i in range(max(0, args.countdown), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...   ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r  Escribiendo nota...            \n")
    sys.stdout.flush()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    done = False
    try:
        place_note(args.text, nx, ny, pause=args.pause, tool_delay=args.tool_delay,
                   type_interval=args.type_interval, focus_xy=(nx, ny))
        ptwindow.park_mouse()
        done = True
    except pyautogui.FailSafeException:
        print("  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except KeyboardInterrupt:
        print("\n  Interrumpido por el usuario.")

    print()
    print("=" * 64)
    print("  RESUMEN")
    print("=" * 64)
    if done:
        print(f'  Nota "{args.text}" colocada en ({nx}, {ny}).')
        print("  Revisa en Packet Tracer:")
        print("    - Aparecio el texto y quedo guardado tras el Escape?")
        print("    - Quedo donde esperabas? (si no, muevela a mano)")
        print("    - Si la tecla 'n' no activo el modo nota, revisa que el foco")
        print("      estuviera en el area de trabajo (no en un campo de texto).")
    else:
        print("  Ejecucion abortada; nada garantizado.")
        sys.exit(1)
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
