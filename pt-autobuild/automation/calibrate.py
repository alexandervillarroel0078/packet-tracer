"""
calibrate.py - Calibracion minima para pt-autobuild (flujo por buscador).

Genera coords.json con solo 3 datos + tamaño de pantalla:

    search_field     centro del campo "Search for device"   (por imagen)
    filtered_result  posicion fija del icono filtrado unico  (manual, 1 vez)
    canvas           rectangulo de trabajo  top_left / bottom_right

El rectangulo del lienzo se deriva de:
    borde superior  = parte inferior de top_toolbar.png
    borde derecho   = borde izquierdo de right_toolbar.png
    borde inferior  = parte superior del campo de busqueda (search_field.png)
    borde izquierdo = valor fijo (el lienzo llega casi al borde de la ventana)

Uso (desde el panel, pestana Calibracion; o como funciones):
    calibrate_by_images(confidence=0.85)          # calibracion por imagenes de referencia
    calibrate_point("canvas_top_left")            # captura UN punto con F8
    list_reference_images()                       # comprobar las imagenes de referencia
    auto_calibrate(dry_run=True)                  # autocalibracion con IA (dry-run por defecto)
    check_calibration()                           # sin API: re-verifica lo guardado

Imagenes de referencia (reference_images/, PNG, nombres EXACTOS):
    search_field.png   recorte del campo "Search for device"
    top_toolbar.png    trozo distintivo de la barra de herramientas superior
    right_toolbar.png  trozo distintivo de la barra vertical derecha

Requiere: pyautogui, opencv-python, Pillow  ->  pip install -r requirements.txt
"""

import os

from core import coords as coords_io
from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui (fija DPI awareness)
from core import paths
from core.errors import PTError
from core.paths import REFERENCE_IMAGES_DIR
from automation import common

import pyautogui

REFDIR = REFERENCE_IMAGES_DIR

MARGIN = 10          # margen general al calcular bordes del lienzo (px)
MARGIN_BOTTOM = 15   # margen por encima del campo de busqueda
MARGIN_LEFT = 12     # borde izquierdo del lienzo (valor fijo)

REF_IMAGES = ["search_field.png", "top_toolbar.png", "right_toolbar.png"]

# --manual <nombre>  ->  (seccion, clave) en coords.json
MANUAL_KEYS = {
    "search_field": ("search_field", None),
    "filtered_result": ("filtered_result", None),
    "canvas_top_left": ("canvas", "top_left"),
    "canvas_bottom_right": ("canvas", "bottom_right"),
}

IMG_NOT_FOUND = getattr(pyautogui, "ImageNotFoundException", None)


def set_point(data, section, key, value):
    if key is None:
        data[section] = value
    else:
        data.setdefault(section, {})[key] = value


def get_point(data, section, key):
    if key is None:
        return data.get(section)
    return data.get(section, {}).get(key)


# --- localizacion por imagen ---------------------------------------
def has_opencv():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def locate(name, confidence, grayscale, use_conf):
    """Devuelve (box|None, error|None)."""
    path = os.path.join(REFDIR, name)
    if not os.path.exists(path):
        return None, f"falta el archivo reference_images/{name}"
    kwargs = {"grayscale": grayscale}
    if use_conf:
        kwargs["confidence"] = confidence
    try:
        box = pyautogui.locateOnScreen(path, **kwargs)
    except Exception as e:  # noqa: BLE001
        if IMG_NOT_FOUND is not None and isinstance(e, IMG_NOT_FOUND):
            return None, "no se encontro en pantalla (sin coincidencia)"
        return None, f"{type(e).__name__}: {e}"
    if box is None:
        return None, "no se encontro en pantalla (sin coincidencia)"
    return box, None


def box_center(box):
    return [int(box.left + box.width / 2), int(box.top + box.height / 2)]


# --- calculo del lienzo -------------------------------------------
def compute_canvas(top_box, right_box, sf_box):
    w, h = pyautogui.size()
    warn = []

    if top_box is not None:
        top = int(top_box.top + top_box.height + MARGIN)
    else:
        top = int(h * 0.12)
        warn.append(f"top_toolbar.png no encontrada: borde superior ESTIMADO a y={top}.")

    if right_box is not None:
        right = int(right_box.left - MARGIN)
    else:
        right = int(w - 60)
        warn.append(f"right_toolbar.png no encontrada: borde derecho ESTIMADO a x={right}.")

    if sf_box is not None:
        bottom = int(sf_box.top - MARGIN_BOTTOM)
    else:
        bottom = int(h * 0.78)
        warn.append(f"search_field.png no encontrada: borde inferior ESTIMADO a y={bottom}.")

    left = MARGIN_LEFT
    if right <= left + 100:
        right = w - 60
        warn.append("borde derecho invalido: forzado.")
    if bottom <= top + 100:
        bottom = int(h * 0.78)
        warn.append("borde inferior invalido: forzado.")

    return {"top_left": [left, top], "bottom_right": [right, bottom]}, warn


# --- modos ------------------------------------------------------
def list_reference_images(log=None):
    """Informa que imagenes de referencia existen. Devuelve {nombre: existe}."""
    log = common.get_log(log)
    log(f"  Carpeta: {REFDIR}   (existe: {os.path.isdir(REFDIR)})")
    log("-" * 50)
    out = {}
    for n in REF_IMAGES:
        p = os.path.join(REFDIR, n)
        out[n] = os.path.exists(p)
        mark = "OK   " if out[n] else "FALTA"
        size = f"{os.path.getsize(p)} B" if out[n] else ""
        log(f"  {mark} {n:<20} {size}")
    return out


def calibrate_point(name, *, countdown=3, log=None, cancel=None):
    """Captura UN punto de coords.json con F8 (ESC cancela). Devuelve [x, y] o None."""
    log = common.get_log(log)
    if name not in MANUAL_KEYS:
        raise PTError(f"punto no valido: {name}. Validos: {', '.join(MANUAL_KEYS)}")
    section, key = MANUAL_KEYS[name]
    data = coords_io.load_coords(paths.COORDS_PATH)
    if name == "filtered_result":
        log("  Antes de capturar: en Packet Tracer haz clic en el buscador, escribe")
        log("  un modelo (ej. 4331) y espera a que aparezca el icono unico filtrado.")
    p = coords_io.capture_point(name, get_point(data, section, key),
                                countdown=countdown, cancel=cancel)
    common.check_cancel(cancel)
    if p is None:
        return None
    set_point(data, section, key, p)
    if not coords_io.save_coords(paths.COORDS_PATH, data):
        raise PTError(f"no se pudo guardar {paths.COORDS_PATH}")
    return p


def calibrate_by_images(*, confidence=0.85, grayscale=False, recapture_result=False,
                        countdown=3, log=None, cancel=None):
    """
    Calibracion de coords.json por imagenes de referencia (reference_images/): localiza
    search_field y las barras para derivar el lienzo; los puntos que no se localizan se
    capturan a mano con F8. Devuelve el dict guardado.
    """
    log = common.get_log(log)
    use_conf = has_opencv()
    coords_path = paths.COORDS_PATH

    log("=" * 70)
    log("  CALIBRACION (flujo por buscador)")
    log("=" * 70)
    log(f"  Resolucion detectada : {tuple(pyautogui.size())}")
    common.dpi_header(log)
    log(f"  Imagenes de ref. en  : {REFDIR}")
    if not use_conf:
        log("  AVISO: opencv-python NO instalado -> match pixel-perfect (mas fragil).")
    else:
        log(f"  Confianza: {confidence}   Grises: {grayscale}")
    log(f"  Salida (ruta absoluta): {coords_path}")
    log("")

    if not os.path.isdir(REFDIR):
        raise PTError(f"no existe la carpeta {REFDIR}. Crea las imagenes: "
                      + ", ".join(REF_IMAGES))

    data = coords_io.load_coords(coords_path)

    # --- Fase A: localizar las 3 imagenes -------------------------
    log("  [Fase A] Localizando imagenes de referencia (Packet Tracer visible)...")
    boxes = {}
    for n in REF_IMAGES:
        common.check_cancel(cancel)
        box, err = locate(n, confidence, grayscale, use_conf)
        boxes[n] = box
        if box is not None:
            log(f"    OK  {n:<18} box=({box.left},{box.top},{box.width},{box.height})")
        else:
            log(f"    XX  {n:<18} {err}")

    if boxes["search_field.png"] is not None:
        sf_center = box_center(boxes["search_field.png"])
        set_point(data, "search_field", None, sf_center)
        log(f"    -> search_field centro = {sf_center}")
    else:
        log("    search_field.png no matcheo; captura el campo de busqueda a mano:")
        p = coords_io.capture_point("search_field", get_point(data, "search_field", None),
                                    countdown=countdown, cancel=cancel)
        common.check_cancel(cancel)
        if p is not None:
            set_point(data, "search_field", None, p)

    # --- filtered_result: manual, solo si falta -----------------
    log("")
    fr = get_point(data, "filtered_result", None)
    if fr is not None and not recapture_result:
        log(f"  [filtered_result] ya calibrado: {fr}  (marca 'recapturar' para rehacerlo)")
    else:
        log("  [filtered_result] Punto fijo del icono filtrado unico.")
        log("  En Packet Tracer: clic en el buscador, escribe un modelo (ej. 4331)")
        log("  y espera a que aparezca el icono. Luego mueve el mouse a su centro.")
        p = coords_io.capture_point("filtered_result", fr, countdown=countdown, cancel=cancel)
        common.check_cancel(cancel)
        if p is not None:
            set_point(data, "filtered_result", None, p)

    # --- Lienzo ----------------------------------------------
    log("")
    log("  [Lienzo] Calculando rectangulo de trabajo...")
    canvas, canvas_warn = compute_canvas(
        boxes["top_toolbar.png"], boxes["right_toolbar.png"], boxes["search_field.png"]
    )
    set_point(data, "canvas", "top_left", canvas["top_left"])
    set_point(data, "canvas", "bottom_right", canvas["bottom_right"])
    log(f"    top_left     = {canvas['top_left']}")
    log(f"    bottom_right = {canvas['bottom_right']}")
    for w in canvas_warn:
        log(f"    [!] {w}")

    saved_ok = coords_io.save_coords(coords_path, data)
    log_summary(data, saved_ok, log)
    if not saved_ok:
        raise PTError(f"no se pudo guardar {coords_path}")
    return data


def log_summary(data, saved_ok, log):
    log("")
    log("=" * 70)
    log("  RESUMEN")
    log("=" * 70)
    rows = [
        ("search_field", None, "Campo de busqueda"),
        ("filtered_result", None, "Resultado filtrado (fijo)"),
        ("canvas", "top_left", "Lienzo: esquina sup-izq"),
        ("canvas", "bottom_right", "Lienzo: esquina inf-der"),
    ]
    missing = []
    for section, key, label in rows:
        val = get_point(data, section, key)
        log(f"  {label:<28} {val if val is not None else 'FALTA'}")
        if val is None:
            missing.append(label)
    log("-" * 70)
    if missing:
        log(f"  Faltan {len(missing)} punto(s). Reejecuta la calibracion o captura el punto a mano.")
    else:
        log("  Todo calibrado. Listo para construir.")
    log("-" * 70)
    if saved_ok:
        log(f"  GUARDADO Y VERIFICADO en: {paths.COORDS_PATH}")
    else:
        log("  ATENCION: no se pudo confirmar el guardado (ver error arriba).")
    log("=" * 70)


def auto_calibrate(*, dry_run=True, force=False, groups="all", test_model="2911",
                   log=None):
    """
    Autocalibracion con IA (core.autocalibrate). dry_run=True (por defecto): solo muestra lo
    detectado; con dry_run=False escribe en el buscador (filtered_result) y guarda.
    groups: "all" o lista/cadena de main, cable, ip. Devuelve 0 (todo ok / cache valida) o 1.
    """
    from core import autocalibrate as ac
    if isinstance(groups, (list, tuple)):
        groups = ",".join(groups)
    return ac.run_autocalibrate(dry_run=dry_run, force=force, groups=ac.parse_groups(groups),
                                test_model=test_model, log=common.get_log(log))


def check_calibration(*, groups="all", dry_run=False, log=None):
    """Sin API: re-verifica los puntos guardados. Devuelve 0 o 1 (hay que recalibrar)."""
    from core import autocalibrate as ac
    if isinstance(groups, (list, tuple)):
        groups = ",".join(groups)
    return ac.run_check(groups=ac.parse_groups(groups), dry_run=dry_run,
                        log=common.get_log(log))
