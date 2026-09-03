"""
move_device.py - Mueve un dispositivo YA colocado en Cisco Packet Tracer.

Aprovecha que data/topology/topologia_actual.json guarda la posicion (x, y)
de cada dispositivo por su nombre. Lee esa posicion actual, arrastra el
dispositivo hasta la nueva posicion y ACTUALIZA el registro para que el
resto de scripts (configure_ip.py, configure_router.py) sigan encontrandolo.

Uso:
    python move_device.py Router0 400 250            # a coordenadas exactas
    python move_device.py Router0 --random           # a un punto aleatorio del lienzo
    python move_device.py Router0 400 250 --dry-run  # plan, sin tocar nada
    python move_device.py PC2 --random --dry-run

Modo (obligatorio, uno de los dos, no ambos):
    X Y            posicion exacta de destino (enteros, en pixeles de pantalla)
    --random      posicion aleatoria dentro del canvas calibrado, con margen

Opciones:
    --margin N     margen con los bordes del canvas para --random (def. 30 px).
    --countdown N  cuenta regresiva antes de arrastrar (def. 5).
    --pause SEG    pausa entre pasos del arrastre (def. 0.4).
    --duration SEG duracion del movimiento suave del arrastre (def. 0.3).
    --topology RUTA  registro alternativo (def. data/topology/topologia_actual.json).
    --dry-run      imprime el plan (actual -> destino) sin mover el mouse ni
                   escribir el JSON.

Limites:
    El destino debe caer dentro del canvas calibrado
    (data/coords.json -> canvas.top_left / canvas.bottom_right). Si no, avisa
    y no ejecuta.

Seguridad:
    - Cuenta regresiva antes de empezar (cambia el foco a Packet Tracer).
    - Failsafe de pyautogui: mouse a la esquina superior izquierda = aborta
      (si aborta a mitad del arrastre NO se actualiza el registro).
"""

import argparse
import json
import os
import random
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui
from core import coords as coords_io
from core.paths import COORDS_PATH, TOPOLOGY_ACTUAL_PATH
from core.topology import load_topology, find_device

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala las dependencias con:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

from core import ptwindow  # noqa: E402  (usa pyautogui; va despues del guard)

DEFAULT_MARGIN = 30  # px de separacion con los bordes del canvas para --random


def load_canvas_box():
    """(x0, y0, x1, y1) del canvas calibrado. Reutiliza core.coords.load_coords."""
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


def save_topology(path, topology):
    """Reescribe el registro completo (mismo formato que build.py) de forma atomica."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(topology, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except OSError as e:
        print(f"  [!] No se pudo actualizar el registro: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
    return True


def countdown(seconds):
    for i in range(max(0, seconds), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...  (cambia el foco a Packet Tracer)   ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r  Arrastrando dispositivo...                                   \n")
    sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(
        description="Mueve (arrastra) un dispositivo ya colocado en Packet Tracer.")
    ap.add_argument("name", help="Nombre del dispositivo, ej. Router0")
    ap.add_argument("x", nargs="?", type=int, default=None, help="Nueva X (px).")
    ap.add_argument("y", nargs="?", type=int, default=None, help="Nueva Y (px).")
    ap.add_argument("--random", action="store_true",
                    help="Destino aleatorio dentro del canvas (en vez de X Y).")
    ap.add_argument("--margin", type=int, default=DEFAULT_MARGIN,
                    help=f"Margen con los bordes para --random (def. {DEFAULT_MARGIN}).")
    ap.add_argument("--topology", default=TOPOLOGY_ACTUAL_PATH,
                    help="Registro de topologia (def. topologia_actual.json).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Imprime el plan sin mover el mouse ni escribir el JSON.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre pasos del arrastre (def. 0.4).")
    ap.add_argument("--duration", type=float, default=0.3,
                    help="Duracion del movimiento suave del arrastre (def. 0.3).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    # --- modo: --random XOR (x, y) --------------------------------------
    has_xy = args.x is not None or args.y is not None
    if args.random and has_xy:
        ap.error("usa --random O coordenadas X Y, no ambos.")
    if not args.random and not has_xy:
        ap.error("indica la nueva posicion: 'X Y' o '--random'.")
    if not args.random and (args.x is None or args.y is None):
        ap.error("faltan coordenadas: se necesitan X e Y (o usa --random).")

    print("=" * 64)
    print("  move_device.py :: mover un dispositivo del lienzo")
    print("=" * 64)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")

    box = load_canvas_box()
    x0, y0, x1, y1 = box
    print(f"  Canvas calibrado: ({x0}, {y0}) -> ({x1}, {y1})")

    topology = load_topology(args.topology)
    device = find_device(topology, args.name)      # sale con error si no existe
    cx, cy = (int(round(device["posicion"][0])), int(round(device["posicion"][1])))

    if args.random:
        tx, ty = random_in_box(box, args.margin)
        print(f"  Destino --random (margen {args.margin}px): ({tx}, {ty})")
    else:
        tx, ty = int(args.x), int(args.y)

    print(f"  Dispositivo: {device['nombre']} "
          f"({device.get('tipo', '?')} {device.get('modelo', '?')})")
    print(f"  Posicion actual : ({cx}, {cy})")
    print(f"  Posicion nueva  : ({tx}, {ty})")

    if not in_box(tx, ty, box):
        print("-" * 64)
        print(f"  ERROR: ({tx}, {ty}) queda FUERA del canvas calibrado.")
        print(f"         X valido: {x0}..{x1}   Y valido: {y0}..{y1}")
        print("  No se ejecuta nada.")
        sys.exit(1)

    if (tx, ty) == (cx, cy):
        print("  Aviso: el destino es igual a la posicion actual; no hay nada que mover.")

    if args.dry_run:
        print("-" * 64)
        print("  Plan:")
        print(f"    1. cuenta regresiva {args.countdown}s")
        print(f"    2. moveTo({cx}, {cy})")
        print("    3. mouseDown()")
        print(f"    4. moveTo({tx}, {ty}, duration={args.duration})")
        print("    5. mouseUp()")
        print(f"    6. actualizar {os.path.basename(args.topology)}: "
              f"{device['nombre']}.posicion = [{tx}, {ty}]")
        print()
        print("  DRY-RUN: no se movera el mouse ni se escribira el JSON.")
        print("=" * 64)
        return

    print()
    print("  Pon el foco en Packet Tracer.")

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0

    countdown(max(0, args.countdown))

    done = False
    try:
        pyautogui.moveTo(cx, cy)
        time.sleep(args.pause)
        pyautogui.mouseDown()
        time.sleep(args.pause)
        pyautogui.moveTo(tx, ty, duration=max(0.0, args.duration))
        time.sleep(args.pause)
        pyautogui.mouseUp()
        time.sleep(args.pause)
        done = True
    except pyautogui.FailSafeException:
        print("  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except KeyboardInterrupt:
        print("\n  Interrumpido por el usuario.")
    finally:
        try:
            pyautogui.mouseUp()  # nunca dejar el boton pulsado
        except Exception:  # noqa: BLE001
            pass
        ptwindow.park_mouse()

    print()
    print("=" * 64)
    print("  RESUMEN")
    print("=" * 64)
    if not done:
        print("  Arrastre incompleto (abortado). El registro NO se actualizo:")
        print(f"    revisa la posicion real de {device['nombre']} en Packet Tracer")
        print("    y, si hace falta, corrige topologia_actual.json a mano.")
        print("=" * 64)
        sys.exit(1)

    device["posicion"] = [tx, ty]
    if save_topology(args.topology, topology):
        print(f"  {device['nombre']}: ({cx}, {cy}) -> ({tx}, {ty})")
        print(f"  Registro actualizado: {args.topology}")
        print("  Revisa en Packet Tracer que el dispositivo quedo donde esperabas.")
    else:
        print(f"  [!] El dispositivo se movio a ({tx}, {ty}) pero NO se pudo")
        print("      actualizar el registro. Los demas scripts usaran la posicion")
        print("      vieja hasta que lo corrijas.")
        print("=" * 64)
        sys.exit(1)
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
