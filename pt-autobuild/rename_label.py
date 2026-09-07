"""
rename_label.py - Renombra la ETIQUETA VISUAL (label debajo del icono) de un
dispositivo YA colocado en el lienzo de Cisco Packet Tracer.

Alcance (a proposito limitado):
    - SOLO el label visual del lienzo (el nombre que se ve debajo del icono,
      ej. "Router11" -> "R01"). NO toca el hostname por CLI del dispositivo
      (eso lo hace, aparte, routers/configure_router.py; no se mezcla aqui).

Estado: EXPERIMENTAL, todavia no confirmado a mano en Packet Tracer.
    A diferencia de add_note.py / configure_ip.py / configure_router.py (que
    documentan un flujo ya probado a mano), este script encapsula una
    HIPOTESIS de como deberia comportarse el rename de un label:

        clic en el label (icono_x, icono_y + offset_y)
        -> Ctrl+A + Supr (defensivo, por si el texto no queda auto-seleccionado)
        -> escribir el nombre nuevo
        -> confirmar: Enter por defecto (a diferencia de una NOTA, que usa
           Escape porque es un cuadro multilinea y Enter le metaria un salto
           de linea; un label de nombre es de una sola linea, asi que Enter
           debería confirmar en vez de cancelar) -- si no funciona, probar
           --confirm-key click-away (clic en un punto vacio del lienzo).

    Probalo aqui, aislado y con --dry-run primero, ANTES de que build.py lo
    use en cadena sobre muchos dispositivos. Si el offset o la tecla de
    confirmacion no coinciden con lo que ves en pantalla, ajustalos con
    --offset-y / --confirm-key (o --away-x/--away-y para click-away) hasta
    confirmar la secuencia; recien ahi conviene integrarlo a build.py.

Reutiliza core/:
    dpi_aware   marca el proceso DPI-aware (antes que pyautogui)
    canvas      limites del lienzo calibrado (para el punto de click-away)
    ptwindow    click_point / park_mouse

Uso (desde pt-autobuild/):
    python rename_label.py 400 250 R01 --category router --dry-run
    python rename_label.py 400 250 R01 --category router
    python rename_label.py 400 250 R01 --category router --offset-y 45
    python rename_label.py 400 250 R01 --category router --confirm-key click-away
    python rename_label.py 400 250 R01 --confirm-key click-away --away-x 50 --away-y 50

Posicion (obligatoria):
    X Y         posicion del ICONO del dispositivo (la misma que uso build.py
                para colocarlo; no la del label -- el offset se suma aqui).

Opciones:
    --category {router,switch,end_device}
                Categoria del dispositivo; decide el offset por defecto
                (def. end_device). Los tres arrancan en 38px (valor de
                partida sin calibrar; ver LABEL_OFFSET_Y mas abajo).
    --offset-y N     Fuerza el offset vertical en px (ignora --category).
    --confirm-key K  Tecla para confirmar el nombre nuevo (def. 'enter').
                     Usa 'click-away' para confirmar con un clic en un punto
                     vacio del lienzo en vez de una tecla.
    --away-x N --away-y N   Punto de "click-away" (def.: esquina superior
                     izquierda del canvas calibrado + 8px de margen, el mismo
                     truco que usa build.py para las notas encadenadas).
    --dry-run        Imprime el plan sin mover el mouse.
    --pause SEG      Pausa entre pasos (def. 0.4).
    --countdown N    Cuenta regresiva antes de empezar (def. 5).

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

# Offset vertical (px) del label respecto del punto donde se coloco el icono.
# VALOR DE ARRANQUE SIN CALIBRAR -- confirmar a mano contra tu Packet Tracer
# (puede variar por categoria si los iconos tienen alturas distintas).
LABEL_OFFSET_Y = {
    "router": 38,
    "switch": 38,
    "end_device": 38,
}
DEFAULT_OFFSET_Y = 38
CATEGORIES = tuple(LABEL_OFFSET_Y)


def rename_label(x, y, new_name, category="end_device", *, pause=0.4,
                 offset_y=None, confirm_key="enter", away_xy=None):
    """Renombra el label de UN dispositivo ya colocado en (x, y). Unica
    fuente de la secuencia de rename (no duplicar esta logica en build.py).

    (x, y) es la posicion del ICONO (la misma que uso build.py al colocarlo),
    no la del label -- el offset vertical se suma aca adentro.

    confirm_key: nombre de tecla para pyautogui.press() (ej. 'enter', 'tab'),
    o el valor especial 'click-away' para confirmar con un clic en un punto
    vacio del lienzo (away_xy, o la esquina superior izquierda del canvas
    calibrado + 8px si no se paso).

    Asume que pyautogui.FAILSAFE lo gestiona el llamador. No hace cuenta
    regresiva. Propaga FailSafeException / KeyboardInterrupt.
    """
    oy = offset_y if offset_y is not None else LABEL_OFFSET_Y.get(category, DEFAULT_OFFSET_Y)
    lx, ly = int(x), int(round(y + oy))

    ptwindow.click_point((lx, ly), pause)
    pyautogui.hotkey("ctrl", "a")             # seleccionar el nombre actual
    time.sleep(0.15)
    pyautogui.press("delete")                 # borrarlo (defensivo; puede
    time.sleep(0.15)                          # que ya quede auto-seleccionado)
    pyautogui.typewrite(str(new_name), interval=0.03)
    time.sleep(pause)

    if confirm_key == "click-away":
        if away_xy is None:
            x0, y0, _x1, _y1 = canvas.load_box()
            away_xy = (x0 + 8, y0 + 8)
        ptwindow.click_point((int(away_xy[0]), int(away_xy[1])), pause)
    else:
        pyautogui.press(confirm_key)
        time.sleep(pause)

    return lx, ly


def main():
    ap = argparse.ArgumentParser(
        description="Renombra el label visual (no el hostname) de un dispositivo "
                    "ya colocado en Packet Tracer.")
    ap.add_argument("x", type=int, help="X del ICONO del dispositivo (px).")
    ap.add_argument("y", type=int, help="Y del ICONO del dispositivo (px).")
    ap.add_argument("new_name", help='Nombre nuevo para el label, ej. "R01"')
    ap.add_argument("--category", choices=CATEGORIES, default="end_device",
                    help="Decide el offset por defecto (def. end_device).")
    ap.add_argument("--offset-y", type=float, default=None,
                    help="Fuerza el offset vertical en px (ignora --category).")
    ap.add_argument("--confirm-key", default="enter",
                    help="Tecla para confirmar (def. 'enter'), o 'click-away' "
                         "para confirmar con un clic en vez de una tecla.")
    ap.add_argument("--away-x", type=int, default=None,
                    help="X del punto de click-away (def. esquina del canvas).")
    ap.add_argument("--away-y", type=int, default=None,
                    help="Y del punto de click-away (def. esquina del canvas).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Imprime el plan sin mover el mouse.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre pasos (def. 0.4).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    print("=" * 64)
    print("  rename_label.py :: renombrar el label visual de un dispositivo")
    print("=" * 64)
    print("  [!] EXPERIMENTAL: secuencia todavia no confirmada a mano (ver docstring).")
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")

    if args.away_x is not None and args.away_y is not None:
        away_xy = (args.away_x, args.away_y)
    elif args.away_x is not None or args.away_y is not None:
        ap.error("--away-x y --away-y van juntos (o ninguno de los dos).")
    else:
        away_xy = None

    oy = args.offset_y if args.offset_y is not None else \
        LABEL_OFFSET_Y.get(args.category, DEFAULT_OFFSET_Y)
    lx, ly = args.x, round(args.y + oy)

    print(f"  Icono   : ({args.x}, {args.y})   categoria: {args.category}")
    print(f"  Label   : ({lx}, {ly})   (offset_y = {oy}px)")
    print(f'  Nombre  : "{args.new_name}"')
    if args.confirm_key == "click-away":
        if away_xy is None:
            x0, y0, _x1, _y1 = canvas.load_box()
            away_xy = (x0 + 8, y0 + 8)
        print(f"  Confirma: clic en ({away_xy[0]}, {away_xy[1]})  [click-away]")
    else:
        print(f"  Confirma: tecla '{args.confirm_key}'")

    if args.dry_run:
        print("-" * 64)
        print("  Plan:")
        print(f"    1. cuenta regresiva {args.countdown}s")
        print(f"    2. clic en el label ({lx}, {ly})")
        print("    3. Ctrl+A + Supr  (borra el nombre actual)")
        print(f'    4. escribir "{args.new_name}"')
        if args.confirm_key == "click-away":
            print(f"    5. clic en ({away_xy[0]}, {away_xy[1]})  (confirma saliendo del campo)")
        else:
            print(f"    5. tecla '{args.confirm_key}'  (confirma)")
        print()
        print("  DRY-RUN: no se movera el mouse.")
        print("=" * 64)
        return

    print()
    print("  Pon el foco en Packet Tracer.")
    for i in range(max(0, args.countdown), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...   ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r  Renombrando...                 \n")
    sys.stdout.flush()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    done = False
    try:
        rename_label(args.x, args.y, args.new_name, category=args.category,
                    pause=args.pause, offset_y=args.offset_y,
                    confirm_key=args.confirm_key, away_xy=away_xy)
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
        print(f'  Label renombrado a "{args.new_name}" en ({lx}, {ly}).')
        print("  Revisa en Packet Tracer:")
        print("    - ¿El clic cayo sobre el texto del label (no sobre el icono)?")
        print("    - ¿Quedo seleccionado/editable el nombre antes de escribir?")
        print("    - ¿La confirmacion funciono (nombre nuevo visible, sin quedar")
        print("      en modo edicion ni revertir al nombre viejo)?")
        print("    - Si algo fallo: ajusta --offset-y y/o --confirm-key y repeti.")
    else:
        print("  Ejecucion abortada; nada garantizado.")
        sys.exit(1)
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
