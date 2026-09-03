"""
configure_router.py - Flujo basico de configuracion de un router por CLI.

    doble clic en el router -> pestana CLI -> (foco consola) -> comandos IOS
    para cambiar el hostname -> cerrar la ventana

Alcance limitado a proposito: SOLO cambia el hostname. No hace
'copy running-config startup-config' ni 'write memory'.

Reutiliza:
    core/                       dpi_aware, coords, ptwindow, validate, topology
    data/topology/topologia_actual.json   posicion (x,y) del router por su nombre
    data/ip_config_coords.json  close_button  (misma ventana, mismo pixel; no se
                                duplica aqui para evitar desincronizacion)

Coordenadas propias de este flujo (data/router_coords.json):
    cli_tab      pestana "CLI" dentro de la ventana del dispositivo   (obligatorio)
    cli_console  punto dentro del area de texto de la consola          (opcional;
                 "skip" si al abrir CLI el foco ya cae solo en la consola)

Uso (ejecutar desde pt-autobuild/):
    python routers/configure_router.py Router0 R01
    python routers/configure_router.py Router0 R01 --dry-run
    python routers/configure_router.py --calibrate
    python routers/configure_router.py Router0 R01 --recalibrate

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre clics/comandos.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import dpi_aware  # noqa: E402,F401  DEBE ir antes de pyautogui
from core import coords as coords_io  # noqa: E402
from core import ptwindow, validate  # noqa: E402
from core.topology import load_topology, find_device  # noqa: E402
from core.paths import (IP_CONFIG_COORDS_PATH, ROUTER_COORDS_PATH,  # noqa: E402
                        TOPOLOGY_ACTUAL_PATH)

import pyautogui  # noqa: E402

SKIP = "skip"

# puntos propios, en orden de calibracion
ROUTER_POINTS = [
    ("cli_tab", "pestana 'CLI'"),
    ("cli_console", "area de consola (Q si el foco ya cae solo)"),
]


def get_close_button():
    """close_button vive en data/ip_config_coords.json (fuente unica)."""
    return coords_io.load_coords(IP_CONFIG_COORDS_PATH).get("close_button")


def calibrate_router(data, only_missing):
    print()
    print("  CALIBRACION de data/router_coords.json")
    print("  En Packet Tracer, haz DOBLE CLIC en un router para abrir su ventana.")
    print("  NO la muevas. Marca la pestana 'CLI'. Para 'cli_console': entra a CLI")
    print("  y, si el foco ya esta en la consola, pulsa Q para guardarlo como 'skip'.")
    print("-" * 64)
    changed = False
    for key, label in ROUTER_POINTS:
        if only_missing and data.get(key) is not None:
            print(f"  {key:<12} ya calibrado: {data[key]}")
            continue
        p = coords_io.capture_point(label, data.get(key))
        if p is None:
            if key == "cli_console":
                data[key] = SKIP
                changed = True
                print(f"    -> '{key}' guardado como '{SKIP}' (no se hara clic)")
            continue
        data[key] = p
        changed = True
    if changed:
        coords_io.save_coords(ROUTER_COORDS_PATH, data)
    return data.get("cli_tab") is not None


def run_cli_sequence(hostname, cmd_pause):
    """[Enter] -> enable -> configure terminal -> hostname X -> end."""
    pyautogui.press("enter")
    time.sleep(cmd_pause)
    for cmd in ("enable", "configure terminal", f"hostname {hostname}", "end"):
        pyautogui.typewrite(cmd, interval=0.03)
        pyautogui.press("enter")
        time.sleep(cmd_pause)


def main():
    ap = argparse.ArgumentParser(
        description="Cambia el hostname de un router via CLI en Packet Tracer.")
    ap.add_argument("name", nargs="?", help="Nombre del router en topologia_actual.json")
    ap.add_argument("hostname", nargs="?", help="Nuevo hostname, ej. R01")
    ap.add_argument("--topology", default=TOPOLOGY_ACTUAL_PATH,
                    help="Registro de topologia (def. data/topology/topologia_actual.json).")
    ap.add_argument("--calibrate", action="store_true",
                    help="Calibrar los puntos de router y salir.")
    ap.add_argument("--recalibrate", action="store_true",
                    help="Recapturar los puntos de router antes de ejecutar.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Imprime el plan sin mover el mouse.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre clics (def. 0.4).")
    ap.add_argument("--open-delay", type=float, default=0.5,
                    help="Espera tras el doble clic (def. 0.5).")
    ap.add_argument("--tab-delay", type=float, default=0.4,
                    help="Espera tras clicar la pestana CLI (def. 0.4).")
    ap.add_argument("--cmd-pause", type=float, default=0.6,
                    help="Pausa entre comandos IOS (def. 0.6).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    print("=" * 64)
    print("  configure_router.py :: cambiar hostname via CLI")
    print("=" * 64)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")
    print(f"  Coords router : {ROUTER_COORDS_PATH}")
    print(f"  close_button  : {IP_CONFIG_COORDS_PATH} (reutilizado)")

    data = coords_io.load_coords(ROUTER_COORDS_PATH)

    if args.calibrate:
        done = calibrate_router(data, only_missing=False)
        print("-" * 64)
        print("  Calibracion completa." if done else "  Falta 'cli_tab' por capturar.")
        return

    if not (args.name and args.hostname):
        ap.error("Indica: NOMBRE HOSTNAME (o usa --calibrate).")

    if not validate.valid_hostname(args.hostname):
        ap.error(f"hostname '{args.hostname}' invalido: empieza por letra, solo "
                 f"letras/digitos/guiones, sin guion final, max 63.")

    topology = load_topology(args.topology)
    device = find_device(topology, args.name)
    if device["tipo"] != "router":
        ap.error(f"'{device['nombre']}' es tipo '{device['tipo']}', no 'router'. "
                 f"Este flujo es solo para routers.")
    dx, dy = device["posicion"]
    close_btn = get_close_button()

    print(f"  Router: {device['nombre']} ({device['modelo']}) en ({dx}, {dy})")

    if args.dry_run:
        console = data.get("cli_console", "SIN CALIBRAR")
        print()
        print("  Plan:")
        print(f"    1. doble clic en ({dx}, {dy})")
        print(f"    2. esperar {args.open_delay}s")
        print(f"    3. clic 'CLI'        {data.get('cli_tab', 'SIN CALIBRAR')}")
        print(f"    4. clic consola      {console}"
              + ("  (se salta)" if console == SKIP else ""))
        print(f"    5. secuencia CLI (pausa {args.cmd_pause}s entre lineas):")
        print("         [Enter]")
        for cmd in ("enable", "configure terminal",
                    f"hostname {args.hostname}", "end"):
            print(f"         {cmd}  [Enter]")
        print(f"    6. clic X (cerrar)   {close_btn if close_btn else 'FALTA en ip_config_coords.json'}")
        print()
        print("  DRY-RUN: no se movera el mouse.")
        print("=" * 64)
        return

    if args.recalibrate:
        calibrate_router(data, only_missing=False)

    if data.get("cli_tab") is None:
        print("  Falta 'cli_tab'. Vamos a calibrarlo.")
        if not calibrate_router(data, only_missing=True):
            print("  Calibracion incompleta. Aborta.")
            sys.exit(1)
    if close_btn is None:
        print("  ERROR: no hay 'close_button' en data/ip_config_coords.json.")
        print("  Calibralo con:  python configure_ip.py --calibrate")
        sys.exit(1)

    print()
    print("  Plan: doble clic router -> CLI -> comandos hostname -> cerrar")
    print("  Pon el foco en Packet Tracer. La ventana del router se abrira sola.")
    for i in range(max(0, args.countdown), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...   ")
        sys.stdout.flush()
        time.sleep(1)
    print("\r  Ejecutando...                    ")

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    done = False
    try:
        ptwindow.open_device_window(dx, dy, args.open_delay)
        ptwindow.click_point(data["cli_tab"], args.tab_delay)

        if data.get("cli_console") not in (None, SKIP):
            ptwindow.click_point(data["cli_console"], args.pause)

        run_cli_sequence(args.hostname, args.cmd_pause)

        ptwindow.close_window(close_btn, args.pause)
        ptwindow.park_mouse()
        done = True
    except pyautogui.FailSafeException:
        print("  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except KeyboardInterrupt:
        print("\n  Interrumpido por el usuario.")

    print()
    print("=" * 64)
    print("  RESUMEN")
    print("=" * 64)
    if done:
        print(f"  {device['nombre']}: hostname -> {args.hostname}")
        print("  Revisa en Packet Tracer:")
        print("    - Se abrio la ventana del router correcto?")
        print("    - El prompt cambio a  {}(config)#  y luego  {}#  ?".format(
            args.hostname, args.hostname))
        print("    - La ventana se cerro?")
        print("  (No se guardo la config: falta 'copy run start', fuera de alcance.)")
    else:
        print("  Ejecucion abortada; nada garantizado.")
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
