"""
core.coords - lectura/escritura de los JSON de coordenadas y captura manual.

    load_coords(path)         -> dict  (o {} si no existe / no se puede leer)
    save_coords(path, data)   -> bool  (escritura atomica + verificacion, anade screen_size)
    capture_point(label, ...) -> [x, y] | None  (mueve el mouse + ESPACIO; Q cancela)
"""

import json
import os
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
import pyautogui

try:
    import msvcrt  # captura manual de puntos (Windows)
except ImportError:
    msvcrt = None


def load_coords(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print(f"  Aviso: {os.path.basename(path)} existe pero no se pudo leer; se ignora.")
        return {}


def save_coords(path, data):
    """Escribe el JSON de forma atomica (con screen_size) y verifica que quedo."""
    data["screen_size"] = list(pyautogui.size())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        print(f"  ERROR al guardar {os.path.basename(path)}: {type(e).__name__}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
    ok = os.path.exists(path)
    print(f"  {'OK' if ok else 'ERROR'}: {os.path.basename(path)} "
          f"{'guardado y verificado' if ok else 'NO se escribio'}.")
    return ok


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
