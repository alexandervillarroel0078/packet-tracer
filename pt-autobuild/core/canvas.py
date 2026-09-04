"""
core.canvas - limites del lienzo de Packet Tracer, leidos de la calibracion.

El rectangulo de trabajo se guarda en data/coords.json bajo 'canvas'
(top_left / bottom_right), lo genera calibrate.py. Varios scripts necesitan
lo mismo: comprobar que un punto cae dentro del lienzo o sacar uno al azar.

    load_box()                 -> (x0, y0, x1, y1)   (sale con error si falta)
    in_box(x, y, box)          -> bool
    random_in_box(box, margin) -> (x, y)             (con margen a los bordes)
"""

import random
import sys

from core import coords as coords_io
from core.paths import COORDS_PATH


def load_box():
    """(x0, y0, x1, y1) normalizado. sys.exit(1) con instrucciones si falta."""
    coords = coords_io.load_coords(COORDS_PATH)
    canvas = coords.get("canvas") or {}
    tl, br = canvas.get("top_left"), canvas.get("bottom_right")
    if not (isinstance(tl, (list, tuple)) and isinstance(br, (list, tuple))
            and len(tl) == 2 and len(br) == 2):
        print(f"ERROR: faltan canvas.top_left / canvas.bottom_right en {COORDS_PATH}")
        print("  Calibra las esquinas:")
        print("    python calibrate.py --manual canvas_top_left")
        print("    python calibrate.py --manual canvas_bottom_right")
        sys.exit(1)
    x0, x1 = sorted((int(round(tl[0])), int(round(br[0]))))
    y0, y1 = sorted((int(round(tl[1])), int(round(br[1]))))
    return x0, y0, x1, y1


def in_box(x, y, box):
    x0, y0, x1, y1 = box
    return x0 <= x <= x1 and y0 <= y <= y1


def random_in_box(box, margin):
    x0, y0, x1, y1 = box
    ax0, ax1 = x0 + margin, x1 - margin
    ay0, ay1 = y0 + margin, y1 - margin
    if ax0 > ax1 or ay0 > ay1:
        print(f"  Aviso: el canvas es mas chico que 2*margen ({margin}px); "
              f"uso el centro.")
        return (x0 + x1) // 2, (y0 + y1) // 2
    return random.randint(ax0, ax1), random.randint(ay0, ay1)
