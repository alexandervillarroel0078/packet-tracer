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

import time

from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui
from core import canvas

import pyautogui

from core import ptwindow  # noqa: E402
from core.errors import PTError
from automation import common

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


def rename_device_label(x, y, new_name, *, category="end_device", offset_y=None,
                        confirm_key="enter", away_xy=None, dry_run=True, pause=0.4,
                        countdown=5, log=None, cancel=None):
    """
    Renombra el label visual (no el hostname) de un dispositivo ya colocado en (x, y).
    dry_run=True (por defecto) solo muestra el plan. EXPERIMENTAL: secuencia no confirmada
    a mano (ver docstring del modulo). Devuelve (lx, ly), la posicion del label.
    """
    log = common.get_log(log)
    if category not in CATEGORIES:
        raise PTError(f"categoria '{category}' no valida. Validas: {', '.join(CATEGORIES)}")
    if not str(new_name).strip():
        raise PTError("indica el nombre nuevo del label.")
    log("=" * 64)
    log("  Renombrar el label visual de un dispositivo")
    log("=" * 64)
    log("  [!] EXPERIMENTAL: secuencia todavia no confirmada a mano (ver docstring).")
    common.dpi_header(log)

    oy = offset_y if offset_y is not None else LABEL_OFFSET_Y.get(category, DEFAULT_OFFSET_Y)
    lx, ly = int(x), round(y + oy)
    log(f"  Icono   : ({x}, {y})   categoria: {category}")
    log(f"  Label   : ({lx}, {ly})   (offset_y = {oy}px)")
    log(f'  Nombre  : "{new_name}"')
    if confirm_key == "click-away":
        if away_xy is None:
            x0, y0, _x1, _y1 = canvas.load_box()
            away_xy = (x0 + 8, y0 + 8)
        log(f"  Confirma: clic en ({away_xy[0]}, {away_xy[1]})  [click-away]")
    else:
        log(f"  Confirma: tecla '{confirm_key}'")

    if dry_run:
        log("-" * 64)
        log("  Plan:")
        log(f"    1. cuenta regresiva {countdown}s")
        log(f"    2. clic en el label ({lx}, {ly})")
        log("    3. Ctrl+A + Supr  (borra el nombre actual)")
        log(f'    4. escribir "{new_name}"')
        if confirm_key == "click-away":
            log(f"    5. clic en ({away_xy[0]}, {away_xy[1]})  (confirma saliendo del campo)")
        else:
            log(f"    5. tecla '{confirm_key}'  (confirma)")
        log("")
        log("  DRY-RUN: no se movera el mouse.")
        return lx, ly

    common.pyautogui_ready()
    common.countdown(countdown, log, cancel)

    def go():
        rename_label(x, y, new_name, category=category, pause=pause, offset_y=offset_y,
                     confirm_key=confirm_key, away_xy=away_xy)
        ptwindow.park_mouse()

    common.run_guarded(go)
    log(f'  Label renombrado a "{new_name}" en ({lx}, {ly}).')
    return lx, ly
