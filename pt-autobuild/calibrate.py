"""
calibrate.py - Calibracion AUTOMATICA por reconocimiento de imagen para pt-autobuild.

Localiza en pantalla los iconos de Cisco Packet Tracer a partir de recortes PNG
guardados en reference_images/, calcula el centro de cada icono y el rectangulo
del lienzo de trabajo, y lo guarda en coords.json con el MISMO formato que espera
build.py (no hay que tocar build.py).

Uso:
    python calibrate.py                     # calibracion automatica completa
    python calibrate.py --confidence 0.80   # baja el umbral si algun icono no matchea
    python calibrate.py --grayscale         # match en gris (a veces mas robusto/rapido)
    python calibrate.py --manual-models     # abre cada categoria tu y pulsas ENTER
    python calibrate.py --no-models         # no toca los modelos
    python calibrate.py --manual categories:router   # captura a mano un punto suelto
    python calibrate.py --list              # solo comprueba que imagenes de ref. hay

Imagenes de referencia (carpeta reference_images/, PNG, nombres EXACTOS):
    router_icon.png    switch_icon.png    pc_icon.png      iconos de CATEGORIA (barra inferior)
    router_model.png   switch_model.png   pc_model.png     icono del MODELO concreto
    top_toolbar.png                                        trozo de la barra superior
    right_toolbar.png                                      trozo de la barra vertical derecha

Requiere: pyautogui, opencv-python, Pillow   ->   pip install -r requirements.txt
(opencv-python solo hace falta para el parametro 'confidence'; sin el, el match
es pixel-perfect y mas fragil.)
"""

import argparse
import json
import os
import sys
import time

import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui (fija DPI awareness)

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala:  pip install -r requirements.txt")
    sys.exit(1)

try:
    import msvcrt  # solo se usa en --manual (Windows)
except ImportError:
    msvcrt = None


HERE = os.path.dirname(os.path.abspath(__file__))
COORDS_PATH = os.path.join(HERE, "coords.json")
REFDIR = os.path.join(HERE, "reference_images")

MARGIN = 10          # margen general al calcular los bordes del lienzo (px)
MARGIN_BOTTOM = 20   # margen por encima de la barra de dispositivos
MARGIN_LEFT = 12     # borde izquierdo del lienzo (valor fijo)

# archivo de referencia -> (seccion en coords.json, clave)
CATEGORY_TARGETS = [
    ("router_icon.png", "categories", "router"),
    ("switch_icon.png", "categories", "switch"),
    ("pc_icon.png",     "categories", "end_devices"),
]
MODEL_TARGETS = [
    ("router_model.png", "models", "router"),
    ("switch_model.png", "models", "switch"),
    ("pc_model.png",     "models", "pc"),
]
ANCHOR_TARGETS = ["top_toolbar.png", "right_toolbar.png"]
ALL_REF_IMAGES = ([n for n, _, _ in CATEGORY_TARGETS]
                  + [n for n, _, _ in MODEL_TARGETS]
                  + ANCHOR_TARGETS)

IMG_NOT_FOUND = getattr(pyautogui, "ImageNotFoundException", None)


# --- utilidades de datos --------------------------------------------------
def load_existing():
    if not os.path.exists(COORDS_PATH):
        return {}
    try:
        with open(COORDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("  Aviso: coords.json existe pero no se pudo leer. Se empezara de cero.")
        return {}


def get_nested(data, section, key):
    return data.get(section, {}).get(key)


def set_nested(data, section, key, value):
    data.setdefault(section, {})[key] = value


def save(data, verbose=False):
    """
    Escribe coords.json de forma atomica y VERIFICA que quedo en disco.
    Devuelve True si el archivo existe despues de escribir, False si no.
    Nunca 'traga' un error en silencio: si algo falla, imprime el error real.
    """
    data["screen_size"] = list(pyautogui.size())
    tmp_path = COORDS_PATH + ".tmp"
    try:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())          # fuerza el vaciado del buffer del SO
        os.replace(tmp_path, COORDS_PATH)  # rename atomico sobre el destino final
    except OSError as e:
        print("\n  ERROR al guardar coords.json:")
        print(f"    {type(e).__name__}: {e}")
        print(f"    Ruta destino : {COORDS_PATH}")
        print(f"    Dir. de trabajo actual: {os.getcwd()}")
        print("    Posibles causas: permisos (Controlled Folder Access / antivirus),")
        print("    carpeta sincronizada (OneDrive) bloqueando la escritura, o el")
        print("    archivo abierto en otro programa.")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False
    except TypeError as e:
        print("\n  ERROR: los datos no son serializables a JSON:")
        print(f"    {e}")
        return False

    exists = os.path.exists(COORDS_PATH)
    if not exists:
        print("\n  ERROR: se escribio sin excepcion pero el archivo NO aparece en:")
        print(f"    {COORDS_PATH}")
        print(f"    (dir. de trabajo actual: {os.getcwd()})")
        return False
    if verbose:
        size = os.path.getsize(COORDS_PATH)
        print(f"  OK: coords.json guardado y verificado ({size} bytes) en:")
        print(f"    {COORDS_PATH}")
    return True


# --- localizacion por imagen --------------------------------------------
def has_opencv():
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False


def ref_path(name):
    return os.path.join(REFDIR, name)


def locate(name, confidence, grayscale, use_conf):
    """
    Devuelve (box, error).
      box   = pyautogui.Box(left, top, width, height) o None
      error = None si OK, o un string describiendo el fallo
    """
    path = ref_path(name)
    if not os.path.exists(path):
        return None, f"falta el archivo reference_images/{name}"
    kwargs = {"grayscale": grayscale}
    if use_conf:
        kwargs["confidence"] = confidence
    try:
        box = pyautogui.locateOnScreen(path, **kwargs)
    except Exception as e:  # noqa: BLE001  (pyscreeze lanza tipos variados)
        if IMG_NOT_FOUND is not None and isinstance(e, IMG_NOT_FOUND):
            return None, "no se encontro en pantalla (sin coincidencia)"
        return None, f"{type(e).__name__}: {e}"
    if box is None:
        return None, "no se encontro en pantalla (sin coincidencia)"
    return box, None


def box_center(box):
    return [int(box.left + box.width / 2), int(box.top + box.height / 2)]


# --- calculo del lienzo -------------------------------------------------
def compute_canvas(boxes):
    """
    boxes: dict {nombre_imagen: box|None}
    Deriva el rectangulo del lienzo de:
      - borde superior : parte inferior de top_toolbar.png
      - borde derecho  : borde izquierdo de right_toolbar.png
      - borde inferior : parte superior del icono de categoria mas alto
      - borde izquierdo: valor fijo (el lienzo llega casi al borde de la ventana)
    Si falta alguna ancla, estima por porcentaje de pantalla y avisa.
    """
    w, h = pyautogui.size()
    warn = []

    top_box = boxes.get("top_toolbar.png")
    right_box = boxes.get("right_toolbar.png")

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

    cat_tops = [boxes[n].top for n, _, _ in CATEGORY_TARGETS
                if boxes.get(n) is not None]
    if cat_tops:
        bottom = int(min(cat_tops) - MARGIN_BOTTOM)
    else:
        bottom = int(h * 0.78)
        warn.append(f"iconos de categoria no encontrados: borde inferior ESTIMADO a y={bottom}.")

    left = MARGIN_LEFT

    if right <= left + 100:
        right = w - 60
        warn.append("borde derecho invalido: forzado.")
    if bottom <= top + 100:
        bottom = int(h * 0.78)
        warn.append("borde inferior invalido: forzado.")

    return {"top_left": [left, top], "bottom_right": [right, bottom]}, warn


# --- fase B: modelos (necesita abrir cada categoria) --------------------
def phase_b_autoclick(data, centers, args, use_conf, results):
    print("  [Fase B] Voy a hacer CLIC en cada icono de categoria para abrir su")
    print("           panel de modelos y localizarlo. Failsafe activo: mueve el")
    print("           mouse a la esquina superior izquierda para abortar.")
    for s in range(5, 0, -1):
        sys.stdout.write(f"\r           Empezando en {s}...  (pon el foco en Packet Tracer)   ")
        sys.stdout.flush()
        time.sleep(1)
    print()
    pyautogui.FAILSAFE = True
    try:
        for name, section, key in MODEL_TARGETS:
            cat_name = name.replace("_model.png", "_icon.png")
            cx, cy = centers[cat_name]
            pyautogui.click(cx, cy)
            time.sleep(0.6)
            box, err = locate(name, args.confidence, args.grayscale, use_conf)
            results[name] = (box, err)
            if box is not None:
                c = box_center(box)
                set_nested(data, section, key, c)
                print(f"    OK  {name:<18} centro={c}")
            else:
                print(f"    XX  {name:<18} {err}")
        w, h = pyautogui.size()
        pyautogui.moveTo(w // 2, h // 2)
    except pyautogui.FailSafeException:
        print("\n    ABORTADO por failsafe durante la Fase B.")


def phase_b_manual(data, args, use_conf, results):
    print("  [Fase B] Para cada modelo: abre TU la categoria en Packet Tracer")
    print("           (un clic en su icono) y pulsa ENTER aqui. No se movera el mouse.")
    for name, section, key in MODEL_TARGETS:
        cat = name.replace("_model.png", "")
        input(f"    -> Abre la categoria '{cat}' y pulsa ENTER...")
        box, err = locate(name, args.confidence, args.grayscale, use_conf)
        results[name] = (box, err)
        if box is not None:
            c = box_center(box)
            set_nested(data, section, key, c)
            print(f"       OK  {name:<18} centro={c}")
        else:
            print(f"       XX  {name:<18} {err}")


# --- resumen -----------------------------------------------------------
def print_summary(data, results, saved_ok):
    print()
    print("=" * 70)
    print("  RESUMEN DE CALIBRACION")
    print("=" * 70)

    rows = [
        ("categories", "router", "Categoria Router"),
        ("categories", "switch", "Categoria Switch"),
        ("categories", "end_devices", "Categoria End Devices"),
        ("models", "router", "Modelo Router"),
        ("models", "switch", "Modelo Switch"),
        ("models", "pc", "Modelo PC"),
        ("canvas", "top_left", "Lienzo: esquina sup-izq"),
        ("canvas", "bottom_right", "Lienzo: esquina inf-der"),
    ]
    missing = []
    for section, key, label in rows:
        val = get_nested(data, section, key)
        status = val if val is not None else "FALTA"
        print(f"  {label:<28} {status}")
        if val is None:
            missing.append(label)

    failed_imgs = [n for n, (box, _) in results.items() if box is None]
    if failed_imgs:
        print("-" * 70)
        print("  Imagenes de referencia que NO matchearon:")
        for n in failed_imgs:
            _, err = results[n]
            print(f"    - {n}: {err}")
        print("  Revisa: recorte demasiado ajustado/ancho, incluye el cursor o un")
        print("  tooltip, JPG en vez de PNG, Packet Tracer tapado, o escala de")
        print("  pantalla distinta a la de cuando recortaste. Prueba --confidence 0.8.")

    print("-" * 70)
    if missing:
        print(f"  Faltan {len(missing)} punto(s). Corrige las imagenes y reejecuta, o usa")
        print("  'python calibrate.py --manual categories:router' para capturar a mano.")
    else:
        print("  Todos los puntos resueltos. Listo para build.py.")
    print("-" * 70)
    if saved_ok:
        print(f"  GUARDADO Y VERIFICADO en: {COORDS_PATH}")
        print(f'  Comprueba con:   Test-Path "{COORDS_PATH}"')
    else:
        print("  ATENCION: NO se pudo confirmar que coords.json quedara en disco")
        print("  (ver error arriba).")
    print("=" * 70)


# --- modo automatico -------------------------------------------------
def run_auto(args):
    use_conf = has_opencv()

    print("=" * 70)
    print("  pt-autobuild :: CALIBRACION AUTOMATICA (reconocimiento de imagen)")
    print("=" * 70)
    print(f"  Resolucion detectada : {tuple(pyautogui.size())}")
    print(f"  DPI awareness        : {dpi_aware.STATUS}")
    _dpi_ok, _dpi_msg = dpi_aware.verify()
    print(f"  {'' if _dpi_ok else '[!] '}{_dpi_msg}")
    print(f"  Directorio de trabajo: {os.getcwd()}")
    print(f"  Imagenes de ref. en  : {REFDIR}")
    if not use_conf:
        print("  AVISO: opencv-python NO instalado -> match pixel-perfect (mas fragil).")
        print("         Instala con:  pip install opencv-python")
    else:
        print(f"  Confianza: {args.confidence}   Grises: {args.grayscale}")
    print(f"  Salida (ruta absoluta): {COORDS_PATH}")
    print()

    if not os.path.isdir(REFDIR):
        print(f"  ERROR: no existe la carpeta {REFDIR}")
        print("  Creala y mete dentro los PNG de referencia. Nombres:")
        for n in ALL_REF_IMAGES:
            print(f"    - {n}")
        sys.exit(1)

    input("  Ten Packet Tracer visible y en modo 'Network Devices'. ENTER para empezar...")

    data = load_existing()
    results = {}       # nombre_imagen -> (box|None, error|None)
    centers = {}       # nombre_imagen -> [x, y]

    # --- Fase A: iconos visibles a la vez -------------------------------
    print()
    print("  [Fase A] Iconos de categoria y anclas de barras...")
    for name, section, key in CATEGORY_TARGETS:
        box, err = locate(name, args.confidence, args.grayscale, use_conf)
        results[name] = (box, err)
        if box is not None:
            c = box_center(box)
            centers[name] = c
            set_nested(data, section, key, c)
            print(f"    OK  {name:<18} centro={c}")
        else:
            print(f"    XX  {name:<18} {err}")

    for name in ANCHOR_TARGETS:
        box, err = locate(name, args.confidence, args.grayscale, use_conf)
        results[name] = (box, err)
        if box is not None:
            print(f"    OK  {name:<18} box=({box.left},{box.top},{box.width},{box.height})")
        else:
            print(f"    XX  {name:<18} {err}")

    # --- Fase B: modelos ---------------------------------------------
    print()
    cats_ok = all(centers.get(n) is not None for n, _, _ in CATEGORY_TARGETS)
    if args.no_models:
        print("  [Fase B] Omitida (--no-models).")
    elif args.manual_models:
        phase_b_manual(data, args, use_conf, results)
    elif not cats_ok:
        print("  [Fase B] Omitida: falta localizar algun icono de categoria (Fase A),")
        print("           no se puede abrir el panel de modelos de forma fiable.")
        print("           Corrige esas imagenes, o usa --manual-models.")
    else:
        phase_b_autoclick(data, centers, args, use_conf, results)

    # --- Lienzo -----------------------------------------------------
    print()
    print("  [Lienzo] Calculando rectangulo de trabajo...")
    boxes = {n: results.get(n, (None, None))[0] for n in ALL_REF_IMAGES}
    canvas, canvas_warn = compute_canvas(boxes)
    set_nested(data, "canvas", "top_left", canvas["top_left"])
    set_nested(data, "canvas", "bottom_right", canvas["bottom_right"])
    print(f"    top_left     = {canvas['top_left']}")
    print(f"    bottom_right = {canvas['bottom_right']}")
    for w in canvas_warn:
        print(f"    [!] {w}")

    saved_ok = save(data, verbose=True)
    print_summary(data, results, saved_ok)


# --- modo --list ---------------------------------------------------
def run_list():
    print(f"  Carpeta: {REFDIR}")
    print(f"  Existe : {os.path.isdir(REFDIR)}")
    print("-" * 50)
    for n in ALL_REF_IMAGES:
        p = ref_path(n)
        mark = "OK " if os.path.exists(p) else "FALTA"
        size = f"{os.path.getsize(p)} B" if os.path.exists(p) else ""
        print(f"  {mark:<6} {n:<20} {size}")


# --- modo --manual (captura a mano de un punto suelto) -----------------
def run_manual(spec):
    if msvcrt is None:
        print("ERROR: --manual requiere Windows (modulo msvcrt).")
        sys.exit(1)
    try:
        section, key = spec.split(":", 1)
    except ValueError:
        print("Formato: --manual seccion:clave   (ej. categories:router, canvas:top_left)")
        sys.exit(1)
    valid = {
        "categories": {"router", "switch", "end_devices"},
        "models": {"router", "switch", "pc"},
        "canvas": {"top_left", "bottom_right"},
    }
    if section not in valid or key not in valid[section]:
        print(f"Punto no valido: {spec}")
        print("Validos:")
        for s, ks in valid.items():
            for k in sorted(ks):
                print(f"  {s}:{k}")
        sys.exit(1)

    data = load_existing()
    print(f"  Captura manual de {section}:{key}")
    print("  Mueve el mouse al punto exacto y pulsa ESPACIO. [Q] cancelar.")
    while msvcrt.kbhit():
        msvcrt.getch()
    while True:
        x, y = pyautogui.position()
        sys.stdout.write(f"\r  Mouse: x={x:>5} y={y:>5}   ")
        sys.stdout.flush()
        if msvcrt.kbhit():
            ch = msvcrt.getch()
            if ch == b" ":
                pos = list(pyautogui.position())
                set_nested(data, section, key, pos)
                print(f"\n  Capturado: {pos}")
                break
            if ch in (b"q", b"Q", b"\x1b"):
                print("\n  Cancelado.")
                return
        time.sleep(0.03)
    save(data, verbose=True)


def main():
    ap = argparse.ArgumentParser(description="Calibracion automatica por imagen para pt-autobuild.")
    ap.add_argument("--confidence", type=float, default=0.85,
                    help="Umbral de coincidencia 0-1 (def. 0.85). Necesita opencv-python.")
    ap.add_argument("--grayscale", action="store_true",
                    help="Buscar en escala de grises (a veces mas robusto/rapido).")
    ap.add_argument("--manual-models", action="store_true",
                    help="Fase B sin autoclic: abres tu cada categoria y pulsas ENTER.")
    ap.add_argument("--no-models", action="store_true",
                    help="No calibrar los modelos (conserva los previos).")
    ap.add_argument("--manual", metavar="SECCION:CLAVE", default=None,
                    help="Captura a mano un punto suelto (ej. canvas:top_left).")
    ap.add_argument("--list", action="store_true",
                    help="Solo comprobar que imagenes de referencia hay.")
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
