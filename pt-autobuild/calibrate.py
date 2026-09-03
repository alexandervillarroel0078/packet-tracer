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

Uso:
    python calibrate.py                    # calibracion completa
    python calibrate.py --confidence 0.80  # baja el umbral si algo no matchea
    python calibrate.py --grayscale
    python calibrate.py --manual filtered_result     # recapturar solo ese punto
    python calibrate.py --manual canvas_top_left     # forzar una esquina a mano
    python calibrate.py --list             # comprobar las imagenes de referencia

Imagenes de referencia (reference_images/, PNG, nombres EXACTOS):
    search_field.png   recorte del campo "Search for device"
    top_toolbar.png    trozo distintivo de la barra de herramientas superior
    right_toolbar.png  trozo distintivo de la barra vertical derecha

Requiere: pyautogui, opencv-python, Pillow  ->  pip install -r requirements.txt
"""

import argparse
import json
import os
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui (fija DPI awareness)
from core.paths import COORDS_PATH, REFERENCE_IMAGES_DIR

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala:  pip install -r requirements.txt")
    sys.exit(1)

try:
    import msvcrt  # captura manual de puntos (Windows)
except ImportError:
    msvcrt = None


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


# --- datos ------------------------------------------------------------
def load_existing():
    if not os.path.exists(COORDS_PATH):
        return {}
    try:
        with open(COORDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("  Aviso: coords.json existe pero no se pudo leer. Se empezara de cero.")
        return {}


def save(data, verbose=False):
    """
    Escribe coords.json de forma atomica y VERIFICA que quedo en disco.
    Devuelve True/False. No 'traga' errores: si falla, imprime el error real.
    """
    data["screen_size"] = list(pyautogui.size())
    os.makedirs(os.path.dirname(COORDS_PATH), exist_ok=True)
    tmp = COORDS_PATH + ".tmp"
    try:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, COORDS_PATH)
    except OSError as e:
        print("\n  ERROR al guardar coords.json:")
        print(f"    {type(e).__name__}: {e}")
        print(f"    Ruta destino          : {COORDS_PATH}")
        print(f"    Directorio de trabajo : {os.getcwd()}")
        print("    Causas: permisos (Controlled Folder Access / antivirus), carpeta")
        print("    sincronizada (OneDrive), o el archivo abierto en otro programa.")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
    except TypeError as e:
        print(f"\n  ERROR: datos no serializables a JSON: {e}")
        return False

    if not os.path.exists(COORDS_PATH):
        print("\n  ERROR: se escribio sin excepcion pero el archivo NO aparece en:")
        print(f"    {COORDS_PATH}  (cwd: {os.getcwd()})")
        return False
    if verbose:
        print(f"  OK: coords.json guardado y verificado "
              f"({os.path.getsize(COORDS_PATH)} bytes) en:")
        print(f"    {COORDS_PATH}")
    return True


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


# --- captura manual de un punto -------------------------------------
def capture_point(label, previous=None):
    if msvcrt is None:
        print(f"  ERROR: la captura manual de '{label}' requiere Windows (msvcrt).")
        sys.exit(1)
    print(f"  Captura de '{label}': mueve el mouse al punto exacto y pulsa ESPACIO.")
    if previous is not None:
        print(f"  (valor actual: {previous})")
    print("  [Q] cancelar.")
    while msvcrt.kbhit():
        msvcrt.getch()
    while True:
        x, y = pyautogui.position()
        sys.stdout.write(f"\r    mouse: x={x:>5} y={y:>5}   ")
        sys.stdout.flush()
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b" ":
                p = [int(x), int(y)]
                print(f"\n    -> {p}")
                return p
            if ch in (b"q", b"Q", b"\x1b"):
                print("\n    cancelado.")
                return None
        time.sleep(0.03)


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
def run_list():
    print(f"  Carpeta: {REFDIR}   (existe: {os.path.isdir(REFDIR)})")
    print("-" * 50)
    for n in REF_IMAGES:
        p = os.path.join(REFDIR, n)
        mark = "OK   " if os.path.exists(p) else "FALTA"
        size = f"{os.path.getsize(p)} B" if os.path.exists(p) else ""
        print(f"  {mark} {n:<20} {size}")


def run_manual(name):
    if name not in MANUAL_KEYS:
        print(f"Punto no valido: {name}")
        print("Validos:", ", ".join(MANUAL_KEYS))
        sys.exit(1)
    section, key = MANUAL_KEYS[name]
    data = load_existing()
    if name == "filtered_result":
        print("  Antes de capturar: en Packet Tracer haz clic en el buscador, escribe")
        print("  un modelo (ej. 4331) y espera a que aparezca el icono unico filtrado.")
    p = capture_point(name, get_point(data, section, key))
    if p is None:
        return
    set_point(data, section, key, p)
    save(data, verbose=True)


def run_auto(args):
    use_conf = has_opencv()

    print("=" * 70)
    print("  pt-autobuild :: CALIBRACION (flujo por buscador)")
    print("=" * 70)
    print(f"  Resolucion detectada : {tuple(pyautogui.size())}")
    print(f"  DPI awareness        : {dpi_aware.STATUS}")
    _ok, _msg = dpi_aware.verify()
    print(f"  {'' if _ok else '[!] '}{_msg}")
    print(f"  Directorio de trabajo: {os.getcwd()}")
    print(f"  Imagenes de ref. en  : {REFDIR}")
    if not use_conf:
        print("  AVISO: opencv-python NO instalado -> match pixel-perfect (mas fragil).")
    else:
        print(f"  Confianza: {args.confidence}   Grises: {args.grayscale}")
    print(f"  Salida (ruta absoluta): {COORDS_PATH}")
    print()

    if not os.path.isdir(REFDIR):
        print(f"  ERROR: no existe la carpeta {REFDIR}. Creala con los PNG:")
        for n in REF_IMAGES:
            print(f"    - {n}")
        sys.exit(1)

    input("  Ten Packet Tracer visible (no hace falta abrir ninguna categoria). ENTER...")

    data = load_existing()

    # --- Fase A: localizar las 3 imagenes -------------------------
    print()
    print("  [Fase A] Localizando imagenes de referencia...")
    boxes = {}
    for n in REF_IMAGES:
        box, err = locate(n, args.confidence, args.grayscale, use_conf)
        boxes[n] = box
        if box is not None:
            print(f"    OK  {n:<18} box=({box.left},{box.top},{box.width},{box.height})")
        else:
            print(f"    XX  {n:<18} {err}")

    if boxes["search_field.png"] is not None:
        sf_center = box_center(boxes["search_field.png"])
        set_point(data, "search_field", None, sf_center)
        print(f"    -> search_field centro = {sf_center}")
    else:
        print("    search_field.png no matcheo; captura el campo de busqueda a mano:")
        p = capture_point("search_field", get_point(data, "search_field", None))
        if p is not None:
            set_point(data, "search_field", None, p)

    # --- filtered_result: manual, solo si falta -----------------
    print()
    fr = get_point(data, "filtered_result", None)
    if fr is not None and not args.recapture_result:
        print(f"  [filtered_result] ya calibrado: {fr}  (usa --manual filtered_result "
              f"o --recapture-result para rehacerlo)")
    else:
        print("  [filtered_result] Punto fijo del icono filtrado unico.")
        print("  En Packet Tracer: clic en el buscador, escribe un modelo (ej. 4331)")
        print("  y espera a que aparezca el icono. Luego mueve el mouse a su centro.")
        p = capture_point("filtered_result", fr)
        if p is not None:
            set_point(data, "filtered_result", None, p)

    # --- Lienzo ----------------------------------------------
    print()
    print("  [Lienzo] Calculando rectangulo de trabajo...")
    canvas, canvas_warn = compute_canvas(
        boxes["top_toolbar.png"], boxes["right_toolbar.png"], boxes["search_field.png"]
    )
    set_point(data, "canvas", "top_left", canvas["top_left"])
    set_point(data, "canvas", "bottom_right", canvas["bottom_right"])
    print(f"    top_left     = {canvas['top_left']}")
    print(f"    bottom_right = {canvas['bottom_right']}")
    for w in canvas_warn:
        print(f"    [!] {w}")

    saved_ok = save(data, verbose=True)
    print_summary(data, saved_ok)


def print_summary(data, saved_ok):
    print()
    print("=" * 70)
    print("  RESUMEN")
    print("=" * 70)
    rows = [
        ("search_field", None, "Campo de busqueda"),
        ("filtered_result", None, "Resultado filtrado (fijo)"),
        ("canvas", "top_left", "Lienzo: esquina sup-izq"),
        ("canvas", "bottom_right", "Lienzo: esquina inf-der"),
    ]
    missing = []
    for section, key, label in rows:
        val = get_point(data, section, key)
        print(f"  {label:<28} {val if val is not None else 'FALTA'}")
        if val is None:
            missing.append(label)
    print("-" * 70)
    if missing:
        print(f"  Faltan {len(missing)} punto(s). Reejecuta calibrate.py o usa")
        print("  'python calibrate.py --manual <nombre>'.")
    else:
        print("  Todo calibrado. Listo para build.py.")
    print("-" * 70)
    if saved_ok:
        print(f"  GUARDADO Y VERIFICADO en: {COORDS_PATH}")
        print(f'  Comprueba:  Test-Path "{COORDS_PATH}"')
    else:
        print("  ATENCION: no se pudo confirmar el guardado (ver error arriba).")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="Calibracion minima para pt-autobuild.")
    ap.add_argument("--confidence", type=float, default=0.85,
                    help="Umbral de coincidencia 0-1 (def. 0.85). Necesita opencv-python.")
    ap.add_argument("--grayscale", action="store_true",
                    help="Buscar en escala de grises.")
    ap.add_argument("--recapture-result", action="store_true",
                    help="Volver a capturar filtered_result aunque ya exista.")
    ap.add_argument("--manual", metavar="NOMBRE", default=None,
                    help="Captura a mano un punto: " + ", ".join(MANUAL_KEYS))
    ap.add_argument("--list", action="store_true",
                    help="Solo comprobar las imagenes de referencia.")
    args = ap.parse_args()

    if args.list:
        run_list()
    elif args.manual:
        run_manual(args.manual)
    else:
        run_auto(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
