"""
core.annotate - guarda la captura enviada a la IA con los puntos devueltos dibujados
(data/ultima_calibracion.png). Solo Pillow; sin tkinter. Es diagnostico: nunca debe romper
la calibracion, asi que save_last_calibration() traga sus propios errores y devuelve la ruta
o None.
"""

import os

from core import paths

COLOR_OK = (255, 225, 77)
COLOR_BAD = (255, 59, 59)


def last_calibration_path():
    return os.path.join(paths.DATA_DIR, "ultima_calibracion.png")


def draw_points(img, sent_size, points, rejected=()):
    """Copia RGB de img a sent_size con cruz + nombre en cada punto {nombre: (x, y)}."""
    from PIL import Image, ImageDraw
    out = img.convert("RGB")
    if out.size != tuple(sent_size):
        out = out.resize(tuple(sent_size), Image.LANCZOS)
    d = ImageDraw.Draw(out)
    for name, (x, y) in points.items():
        color = COLOR_BAD if name in rejected else COLOR_OK
        r = 9
        d.line((x - r, y, x + r, y), fill=(0, 0, 0), width=4)
        d.line((x, y - r, x, y + r), fill=(0, 0, 0), width=4)
        d.line((x - r, y, x + r, y), fill=color, width=2)
        d.line((x, y - r, x, y + r), fill=color, width=2)
        d.ellipse((x - r, y - r, x + r, y + r), outline=color, width=2)
        label = name + (" (RECHAZADO)" if name in rejected else "")
        d.text((x + r + 4, y - 6), label, fill=(0, 0, 0))
        d.text((x + r + 3, y - 7), label, fill=color)
    return out


def save_last_calibration(img, sent_size, points, rejected=(), path=None):
    path = path or last_calibration_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        draw_points(img, sent_size, points, rejected).save(path)
        return path
    except Exception:  # noqa: BLE001 - diagnostico, nunca debe romper la calibracion
        return None
