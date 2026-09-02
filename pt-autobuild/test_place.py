"""
test_place.py - Prueba el flujo SIMPLIFICADO de colocacion de un dispositivo.

Valida, con UN solo dispositivo, la secuencia de 6 pasos que usara build.py:

    1. clic en el campo de busqueda "Search for device"
    2. Ctrl+A + Supr           (limpiar texto previo)
    3. escribir el nombre del modelo   (filtra en vivo, sin Enter)
    4. esperar a que filtre
    5. clic en el resultado unico (posicion fija = filtered_result)
    6. clic en el lienzo

NO abre ninguna categoria: el buscador de Packet Tracer es global y siempre
visible desde que arranca el programa.

Uso:
    python test_place.py                  # coloca "4331" en el centro del lienzo
    python test_place.py 2960             # otro modelo
    python test_place.py PC --at 600,400  # modelo y punto del lienzo explicitos
    python test_place.py 4331 --save      # guarda en coords.json los puntos capturados

Lee de coords.json:  search_field, filtered_result, canvas (top_left/bottom_right).
  - Sin search_field    -> intenta localizar reference_images/search_field.png;
                           si no, lo capturas moviendo el mouse + ESPACIO.
  - Sin filtered_result -> lo capturas moviendo el mouse + ESPACIO (solo aparece
                           tras escribir en el buscador; no se puede localizar por imagen).

Seguridad: cuenta regresiva de 5 s, failsafe de pyautogui (mouse a la esquina
superior izquierda aborta), pausa configurable entre clics.
"""

import argparse
import json
import os
import sys
import time

import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui (fija DPI awareness)
import pyautogui

try:
    import msvcrt
except ImportError:
    msvcrt = None

HERE = os.path.dirname(os.path.abspath(__file__))
COORDS_PATH = os.path.join(HERE, "coords.json")
SEARCH_FIELD_IMG = os.path.join(HERE, "reference_images", "search_field.png")

IMG_NOT_FOUND = getattr(pyautogui, "ImageNotFoundException", None)


def load_coords():
    if not os.path.exists(COORDS_PATH):
        return {}
    try:
        with open(COORDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("  Aviso: coords.json no se pudo leer; se ignora.")
        return {}


def save_coords(data):
    tmp = COORDS_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, COORDS_PATH)
    except OSError as e:
        print(f"  ERROR al guardar coords.json: {type(e).__name__}: {e}")
        return False
    ok = os.path.exists(COORDS_PATH)
    print(f"  {'OK' if ok else 'ERROR'}: coords.json "
          f"{'guardado y verificado' if ok else 'NO se escribio'}.")
    return ok


def capture_point(label):
    if msvcrt is None:
        print(f"  ERROR: la captura manual de '{label}' requiere Windows (msvcrt).")
        sys.exit(1)
    print(f"  Captura de '{label}': mueve el mouse al punto exacto y pulsa ESPACIO. [Q] aborta.")
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
                print("\n    abortado.")
                sys.exit(1)
        time.sleep(0.03)


def locate_search_field(confidence):
    if not os.path.exists(SEARCH_FIELD_IMG):
        return None
    kwargs = {"confidence": confidence}
    try:
        import cv2  # noqa: F401
    except ImportError:
        kwargs = {}  # sin opencv no se puede usar confidence
    try:
        box = pyautogui.locateOnScreen(SEARCH_FIELD_IMG, **kwargs)
    except Exception as e:  # noqa: BLE001
        if IMG_NOT_FOUND is not None and isinstance(e, IMG_NOT_FOUND):
            return None
        print(f"  Aviso: locateOnScreen fallo: {type(e).__name__}: {e}")
        return None
    if box is None:
        return None
    c = pyautogui.center(box)
    return [int(c.x), int(c.y)]


def parse_at(s):
    try:
        a, b = s.split(",")
        return [int(a), int(b)]
    except ValueError:
        raise argparse.ArgumentTypeError("--at espera 'X,Y' (ej. 600,400)")


def main():
    ap = argparse.ArgumentParser(
        description="Prueba el flujo simplificado de colocacion con un dispositivo.")
    ap.add_argument("model", nargs="?", default="4331",
                    help="Nombre del modelo a buscar y colocar (def. 4331).")
    ap.add_argument("--at", type=parse_at, default=None,
                    help="Punto del lienzo 'X,Y' (def. centro del canvas calibrado).")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre clics en segundos (def. 0.4).")
    ap.add_argument("--filter-delay", type=float, default=0.4,
                    help="Espera tras escribir, antes de clicar el resultado (def. 0.4).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    ap.add_argument("--confidence", type=float, default=0.8,
                    help="Confianza para localizar search_field.png (def. 0.8).")
    ap.add_argument("--save", action="store_true",
                    help="Guarda en coords.json los puntos capturados a mano.")
    args = ap.parse_args()

    print("=" * 64)
    print("  test_place.py :: prueba de flujo simplificado (1 dispositivo)")
    print("=" * 64)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")
    print()

    data = load_coords()
    captured = False

    # --- search_field --------------------------------------------------
    sf = data.get("search_field")
    if sf is None:
        sf = locate_search_field(args.confidence)
        if sf is not None:
            print(f"  search_field (localizado por imagen): {sf}")
        else:
            print("  search_field: no esta en coords.json ni se pudo localizar por imagen.")
            sf = capture_point("search_field")
            data["search_field"] = sf
            captured = True
    else:
        print(f"  search_field (coords.json): {sf}")

    # --- filtered_result --------------------------------------------
    fr = data.get("filtered_result")
    if fr is None:
        print("  filtered_result: no esta en coords.json.")
        print("  Abre el buscador de Packet Tracer y escribe un modelo para que")
        print("  aparezca el icono unico; luego lleva el mouse a su centro.")
        fr = capture_point("filtered_result")
        data["filtered_result"] = fr
        captured = True
    else:
        print(f"  filtered_result (coords.json): {fr}")

    # --- destino en el lienzo -------------------------------------
    if args.at is not None:
        target = args.at
        print(f"  destino en el lienzo (--at): {target}")
    else:
        c = data.get("canvas", {})
        tl, br = c.get("top_left"), c.get("bottom_right")
        if tl and br:
            target = [(tl[0] + br[0]) // 2, (tl[1] + br[1]) // 2]
            print(f"  destino en el lienzo (centro del canvas): {target}")
        else:
            print("  canvas no calibrado y sin --at.")
            target = capture_point("punto del lienzo")

    if captured:
        if args.save:
            save_coords(data)
        else:
            print("  (usa --save para guardar los puntos capturados en coords.json)")

    # --- plan ----------------------------------------------------
    print()
    print("  Plan:")
    print(f"    1. clic search_field {sf}")
    print("    2. Ctrl+A + Supr")
    print(f"    3. escribir '{args.model}'")
    print(f"    4. esperar {args.filter_delay}s a que filtre")
    print(f"    5. clic filtered_result {fr}")
    print(f"    6. clic lienzo {target}")
    print()

    for i in range(max(0, args.countdown), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...  (pon el foco en Packet Tracer)   ")
        sys.stdout.flush()
        time.sleep(1)
    print("\r  Ejecutando...                                        ")

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    p = args.pause
    done = False
    try:
        pyautogui.click(sf[0], sf[1])
        time.sleep(p)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.15)
        pyautogui.press("delete")
        time.sleep(0.15)
        pyautogui.write(str(args.model), interval=0.05)
        time.sleep(args.filter_delay)
        pyautogui.click(fr[0], fr[1])
        time.sleep(p)
        pyautogui.click(target[0], target[1])
        time.sleep(p)
        w, h = pyautogui.size()
        pyautogui.moveTo(w // 2, h // 2)
        done = True
    except pyautogui.FailSafeException:
        print("  ABORTADO por failsafe (mouse en la esquina superior izquierda).")

    print()
    print("=" * 64)
    print("  RESUMEN")
    print("=" * 64)
    if done:
        print(f"  Intente colocar 1x '{args.model}' en {target}.")
        print("  Revisa en Packet Tracer:")
        print("    - Aparecio EXACTAMENTE ese modelo?   (si no: nombre mal escrito / catalogo)")
        print("    - Cayo donde esperabas?              (si no: recalibra filtered_result o canvas)")
        print("    - El buscador quedo con texto basura? (si si: hay que ajustar el limpiado)")
    else:
        print("  Ejecucion abortada; nada garantizado.")
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
