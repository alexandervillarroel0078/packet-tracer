"""
configure_ip.py - Flujo COMPLETO de configuracion IP de un dispositivo.

    doble clic en el dispositivo -> Desktop -> IP Configuration -> Static
    -> escribir IPv4 / Mascara / Gateway -> cerrar la ventana

Con --skip-open asume que la ventana YA esta abierta y en 'Desktop > IP
Configuration' (modo depuracion): solo escribe los 3 campos y no cierra.

La posicion del dispositivo NO se pasa a mano: se lee de topologia_actual.json
(el registro que genera build.py) buscando el dispositivo por su nombre.

Puntos a calibrar (posicion fija en pantalla; la ventana emergente de Packet
Tracer abre siempre en el mismo sitio mientras no la muevas ni cambies la
resolucion). Todos en data/ip_config_coords.json:

    desktop_tab           pestana "Desktop" dentro de la ventana
    ip_configuration_item icono "IP Configuration" ("skip" si aparece directo)
    static_radio          radio button "Static"
    close_button          boton X de la ventana (lo reutiliza configure_router.py)
    ipv4_address / subnet_mask / default_gateway   campos de texto

Uso:
    python configure_ip.py PC0 192.168.10.10 255.255.255.0 192.168.10.1
    python configure_ip.py PC0 ... --dry-run
    python configure_ip.py PC0 ... --skip-open   # ventana ya abierta (depurar)
    python configure_ip.py --calibrate
    python configure_ip.py PC0 ... --recalibrate

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre clics.
"""

import argparse
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
from core import coords as coords_io
from core import ptwindow, validate
from core.topology import load_topology, find_device
from core.paths import IP_CONFIG_COORDS_PATH, TOPOLOGY_ACTUAL_PATH

import pyautogui

SKIP = "skip"

# campos de texto, en el orden en que se escriben
FIELDS = [
    ("ipv4_address", "IPv4 Address"),
    ("subnet_mask", "Subnet Mask"),
    ("default_gateway", "Default Gateway"),
]

# puntos de navegacion de la ventana, en orden de calibracion
WINDOW_POINTS = [
    ("desktop_tab", "pestana 'Desktop'"),
    ("ip_configuration_item", "icono 'IP Configuration' (Q si aparece directo)"),
    ("static_radio", "radio button 'Static'"),
    ("close_button", "boton X de la ventana"),
]

FIELD_POINTS = [
    ("ipv4_address", "campo 'IPv4 Address'"),
    ("subnet_mask", "campo 'Subnet Mask'"),
    ("default_gateway", "campo 'Default Gateway'"),
]


def calibrate(data, points, only_missing):
    """Captura una lista de (clave, etiqueta). 'skip' vale para ip_configuration_item."""
    changed = False
    for key, label in points:
        if only_missing and data.get(key) is not None:
            print(f"  {key:<22} ya calibrado: {data[key]}")
            continue
        p = coords_io.capture_point(label, data.get(key))
        if p is None:
            if key == "ip_configuration_item":
                data[key] = SKIP
                changed = True
                print(f"    -> '{key}' guardado como '{SKIP}' (no se hara clic)")
            continue
        data[key] = p
        changed = True
    if changed:
        coords_io.save_coords(IP_CONFIG_COORDS_PATH, data)


def run_calibrate(data):
    print()
    print("  CALIBRACION de data/ip_config_coords.json")
    print("  1) En Packet Tracer, DOBLE CLIC en un PC para abrir su ventana. NO la muevas.")
    print("  2) Marca 'Desktop' y el boton X (visibles ya).")
    print("  3) Entra a Desktop > IP Configuration (modo Static) a mano.")
    print("     Para 'IP Configuration': si aparece directo al pulsar Desktop, pulsa Q.")
    print("  4) Marca 'Static' y los 3 campos de texto.")
    print("-" * 64)
    calibrate(data, WINDOW_POINTS + FIELD_POINTS, only_missing=False)
    return all(data.get(k) is not None for k, _ in WINDOW_POINTS + FIELD_POINTS)


def main():
    ap = argparse.ArgumentParser(
        description="Flujo completo: abrir ventana + escribir IP en un dispositivo.")
    ap.add_argument("name", nargs="?", help="Nombre del dispositivo, ej. PC0")
    ap.add_argument("ip", nargs="?", help="IPv4 Address")
    ap.add_argument("mask", nargs="?", help="Subnet Mask")
    ap.add_argument("gateway", nargs="?", help="Default Gateway")
    ap.add_argument("--topology", default=TOPOLOGY_ACTUAL_PATH,
                    help="Registro de topologia (def. data/topology/topologia_actual.json).")
    ap.add_argument("--calibrate", action="store_true",
                    help="Calibrar todos los puntos y salir.")
    ap.add_argument("--recalibrate", action="store_true",
                    help="Recapturar todos los puntos antes de ejecutar.")
    ap.add_argument("--skip-open", action="store_true",
                    help="La ventana ya esta abierta en IP Configuration: solo escribe "
                         "los 3 campos (no abre, no navega, no cierra).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Imprime el plan sin mover el mouse.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre clics (def. 0.4).")
    ap.add_argument("--open-delay", type=float, default=0.5,
                    help="Espera tras el doble clic, a que abra la ventana (def. 0.5).")
    ap.add_argument("--tab-delay", type=float, default=0.4,
                    help="Espera tras cambiar de pestana/pantalla (def. 0.4).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    print("=" * 64)
    print("  configure_ip.py :: abrir ventana + escribir IP")
    print("=" * 64)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")
    print(f"  Coords : {IP_CONFIG_COORDS_PATH}")

    data = coords_io.load_coords(IP_CONFIG_COORDS_PATH)

    if args.calibrate:
        done = run_calibrate(data)
        print("-" * 64)
        print("  Calibracion completa." if done else "  Faltan puntos por capturar.")
        return

    if not (args.name and args.ip and args.mask and args.gateway):
        ap.error("Indica: NOMBRE IP MASCARA GATEWAY (o usa --calibrate).")

    for label, val in (("IP", args.ip), ("mascara", args.mask), ("gateway", args.gateway)):
        if not validate.valid_ipish(val):
            ap.error(f"{label} '{val}' no parece un IPv4 valido (x.x.x.x, 0-255).")

    topology = load_topology(args.topology)
    device = find_device(topology, args.name)
    dx, dy = device["posicion"]
    print(f"  Dispositivo: {device['nombre']} ({device['tipo']} {device['modelo']}) "
          f"en ({dx}, {dy})")
    if device["tipo"] in ("router", "switch"):
        print("  [!] Aviso: routers y switches no tienen pestana 'Desktop'. Este flujo")
        print("      esta pensado para PC / Laptop / Server.")

    values = {"ipv4_address": args.ip, "subnet_mask": args.mask,
              "default_gateway": args.gateway}

    if args.skip_open:
        needed = [k for k, _ in FIELDS]
        plan_steps = [f"escribir {lbl} {data.get(k, 'SIN CALIBRAR')} <- '{values[k]}'"
                      for k, lbl in FIELDS]
    else:
        needed = [k for k, _ in WINDOW_POINTS] + [k for k, _ in FIELDS]
        plan_steps = [
            f"doble clic en ({dx}, {dy}); esperar {args.open_delay}s",
            f"clic 'Desktop' {data.get('desktop_tab', 'SIN CALIBRAR')}",
        ]
        ipc = data.get("ip_configuration_item", "SIN CALIBRAR")
        plan_steps.append(f"clic 'IP Configuration' {ipc}"
                          + ("  (se salta)" if ipc == SKIP else ""))
        plan_steps.append(f"clic 'Static' {data.get('static_radio', 'SIN CALIBRAR')}")
        plan_steps += [f"escribir {lbl} {data.get(k, 'SIN CALIBRAR')} <- '{values[k]}'"
                       for k, lbl in FIELDS]
        plan_steps.append(f"clic X (cerrar) {data.get('close_button', 'SIN CALIBRAR')}")

    if args.dry_run:
        print()
        print("  Plan:" + ("  [--skip-open]" if args.skip_open else ""))
        for i, step in enumerate(plan_steps, 1):
            print(f"    {i}. {step}")
        print()
        print("  DRY-RUN: no se movera el mouse.")
        print("=" * 64)
        return

    if args.recalibrate:
        run_calibrate(data)

    missing = [k for k in needed if data.get(k) is None]
    if missing:
        print(f"  Faltan puntos: {', '.join(missing)}. Vamos a calibrarlos.")
        calibrate(data, WINDOW_POINTS + FIELD_POINTS, only_missing=True)
        missing = [k for k in needed if data.get(k) is None]
        if missing:
            print(f"  Siguen faltando: {', '.join(missing)}. Aborta.")
            sys.exit(1)

    print()
    if args.skip_open:
        print("  Plan: la ventana debe estar YA en Desktop > IP Configuration.")
    else:
        print("  Plan: doble clic -> Desktop -> IP Configuration -> Static -> 3 campos -> cerrar")
    print("  Pon el foco en Packet Tracer.")
    for i in range(max(0, args.countdown), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...   ")
        sys.stdout.flush()
        time.sleep(1)
    print("\r  Ejecutando...                    ")

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    p = args.pause
    done = False
    try:
        if not args.skip_open:
            ptwindow.open_device_window(dx, dy, args.open_delay)
            ptwindow.click_point(data["desktop_tab"], args.tab_delay)
            if data.get("ip_configuration_item") not in (None, SKIP):
                ptwindow.click_point(data["ip_configuration_item"], args.tab_delay)
            ptwindow.click_point(data["static_radio"], p)

        for key, _ in FIELDS:
            ptwindow.type_into(data[key], values[key], p)

        if not args.skip_open:
            ptwindow.close_window(data["close_button"], p)

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
        print(f"  {device['nombre']}: IPv4 {args.ip} / {args.mask} / GW {args.gateway}")
        print("  Revisa en Packet Tracer:")
        print("    - Se abrio la ventana del dispositivo correcto?" if not args.skip_open
              else "    - Se escribio en la ventana correcta?")
        print("    - Quedo en 'Static' y los 3 campos correctos?")
        if not args.skip_open:
            print("    - La ventana se cerro?")
        print("  Si algo fallo, recalibra:  python configure_ip.py --calibrate")
    else:
        print("  Ejecucion abortada; nada garantizado.")
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
