"""
move_device.py - Mueve un dispositivo YA colocado en Cisco Packet Tracer.

Aprovecha que data/topology/topologia_actual.json guarda la posicion (x, y)
de cada dispositivo por su nombre. Lee esa posicion actual, arrastra el
dispositivo hasta la nueva posicion y ACTUALIZA el registro para que el
resto de flujos (configure_ip, configure_router) sigan encontrandolo.

Uso (desde el panel, pestana Colocar -> "Mover dispositivo"; o desde codigo):
    move_device("Router0", 400, 250, dry_run=False)   # a coordenadas exactas
    move_device("Router0", random_pos=True)           # punto aleatorio del lienzo (dry-run)

dry_run=True es el valor por defecto: muestra el plan (actual -> destino) sin mover el
mouse ni escribir el JSON. Parametros: margin, countdown, pause, duration, topology_path,
log (callback de mensajes) y cancel (threading.Event).

Limites:
    El destino debe caer dentro del canvas calibrado
    (data/coords.json -> canvas.top_left / canvas.bottom_right). Si no, avisa
    y no ejecuta.

Seguridad:
    - Cuenta regresiva antes de empezar (cambia el foco a Packet Tracer).
    - Failsafe de pyautogui: mouse a la esquina superior izquierda = aborta
      (si aborta a mitad del arrastre NO se actualiza el registro).
"""

import json
import os
import time

from core import canvas
from core import paths
from core.errors import PTError
from core.topology import load_topology, find_device

import pyautogui

from core import ptwindow  # noqa: E402
from automation import common

DEFAULT_MARGIN = 30  # px de separacion con los bordes del canvas para posicion aleatoria


def save_topology(path, topology):
    """Reescribe el registro completo (mismo formato que build) de forma atomica."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(topology, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
    return True


def move_device(name, x=None, y=None, *, random_pos=False, margin=DEFAULT_MARGIN,
                topology_path=None, dry_run=True, pause=0.4, duration=0.3, countdown=5,
                log=None, cancel=None):
    """
    Mueve (arrastra) un dispositivo ya colocado y actualiza el registro de topologia.
    dry_run=True (por defecto) solo muestra el plan: no mueve el mouse ni escribe el JSON.
    Devuelve (x_nueva, y_nueva). Lanza PTError (datos invalidos, fuera del canvas, registro
    no actualizable) o CancelledError (cancelado / failsafe; el registro NO se actualiza).
    """
    log = common.get_log(log)
    topology_path = topology_path or paths.TOPOLOGY_ACTUAL_PATH

    has_xy = x is not None or y is not None
    if random_pos and has_xy:
        raise PTError("usa posicion aleatoria O coordenadas X Y, no ambos.")
    if not random_pos and not has_xy:
        raise PTError("indica la nueva posicion: X Y o aleatoria.")
    if not random_pos and (x is None or y is None):
        raise PTError("faltan coordenadas: se necesitan X e Y (o usa posicion aleatoria).")

    log("=" * 64)
    log("  Mover un dispositivo del lienzo")
    log("=" * 64)
    common.dpi_header(log)

    box = canvas.load_box()
    x0, y0, x1, y1 = box
    log(f"  Canvas calibrado: ({x0}, {y0}) -> ({x1}, {y1})")

    topology = load_topology(topology_path)
    device = find_device(topology, name)
    cx, cy = int(round(device["posicion"][0])), int(round(device["posicion"][1]))

    if random_pos:
        tx, ty = canvas.random_in_box(box, margin)
        log(f"  Destino aleatorio (margen {margin}px): ({tx}, {ty})")
    else:
        tx, ty = int(x), int(y)

    log(f"  Dispositivo: {device['nombre']} "
        f"({device.get('tipo', '?')} {device.get('modelo', '?')})")
    log(f"  Posicion actual : ({cx}, {cy})")
    log(f"  Posicion nueva  : ({tx}, {ty})")

    if not canvas.in_box(tx, ty, box):
        raise PTError(f"({tx}, {ty}) queda FUERA del canvas calibrado "
                      f"(X valido: {x0}..{x1}   Y valido: {y0}..{y1}). No se ejecuta nada.")
    if (tx, ty) == (cx, cy):
        log("  Aviso: el destino es igual a la posicion actual; no hay nada que mover.")

    if dry_run:
        log("-" * 64)
        log("  Plan:")
        log(f"    1. cuenta regresiva {countdown}s")
        log(f"    2. moveTo({cx}, {cy})")
        log("    3. mouseDown()")
        log(f"    4. moveTo({tx}, {ty}, duration={duration})")
        log("    5. mouseUp()")
        log(f"    6. actualizar {os.path.basename(topology_path)}: "
            f"{device['nombre']}.posicion = [{tx}, {ty}]")
        log("")
        log("  DRY-RUN: no se movera el mouse ni se escribira el JSON.")
        return tx, ty

    common.pyautogui_ready()
    common.countdown(countdown, log, cancel, text="Empezando en {i}...  (enfoca Packet Tracer)")

    def drag():
        try:
            pyautogui.moveTo(cx, cy)
            time.sleep(pause)
            pyautogui.mouseDown()
            time.sleep(pause)
            pyautogui.moveTo(tx, ty, duration=max(0.0, duration))
            time.sleep(pause)
            pyautogui.mouseUp()
            time.sleep(pause)
        finally:
            try:
                pyautogui.mouseUp()  # nunca dejar el boton pulsado
            except Exception:  # noqa: BLE001
                pass
            ptwindow.park_mouse()

    try:
        common.run_guarded(drag)
    except PTError as e:
        raise type(e)(f"{e}. Arrastre incompleto: el registro NO se actualizo; revisa la "
                      f"posicion real de {device['nombre']} en Packet Tracer.") from e

    device["posicion"] = [tx, ty]
    if not save_topology(topology_path, topology):
        raise PTError(f"el dispositivo se movio a ({tx}, {ty}) pero NO se pudo actualizar el "
                      "registro: los demas flujos usaran la posicion vieja hasta que lo corrijas.")
    log(f"  {device['nombre']}: ({cx}, {cy}) -> ({tx}, {ty})")
    log(f"  Registro actualizado: {topology_path}")
    return tx, ty
