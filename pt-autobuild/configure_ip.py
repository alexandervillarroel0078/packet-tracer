"""
configure_ip.py - Flujo COMPLETO de configuracion IP de un dispositivo.

    doble clic en el dispositivo -> Desktop -> IP Configuration -> Static
    -> escribir IPv4 / Mascara / Gateway -> cerrar la ventana

Reutiliza la logica de escritura ya validada en test_configure_ip.py
(capture_point, type_into, valid_ipish, load_coords/save_coords) y su mismo
archivo de coordenadas, ip_config_coords.json.

La posicion del dispositivo NO se pasa a mano: se lee de topologia_actual.json
(el registro que genera build.py) buscando el dispositivo por su nombre.

Puntos que hay que calibrar (todos con posicion fija en pantalla, porque la
ventana emergente de Packet Tracer siempre abre en el mismo sitio mientras no
la muevas ni cambies la resolucion):

    desktop_tab           pestana "Desktop" dentro de la ventana
    ip_configuration_item icono/boton "IP Configuration" en el escritorio
                          (o "skip" si al entrar a Desktop ya se ve directo)
    static_radio          radio button "Static"
    close_button          boton X de la ventana (esquina sup. derecha)
    ipv4_address / subnet_mask / default_gateway   (ya calibrados antes)

Uso:
    python configure_ip.py PC0 192.168.10.10 255.255.255.0 192.168.10.1
    python configure_ip.py PC0 ... --dry-run
    python configure_ip.py --calibrate      # calibrar los puntos de la ventana
    python configure_ip.py PC0 ... --recalibrate

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre clics.
"""

import argparse
import os
import sys
import time

import test_configure_ip as tci  # reutiliza dpi_aware, pyautogui, y la logica probada

pyautogui = tci.pyautogui
dpi_aware = tci.dpi_aware

HERE = os.path.dirname(os.path.abspath(__file__))
TOPOLOGY_PATH = os.path.join(HERE, "topologia_actual.json")

# puntos nuevos de la ventana emergente, en el orden de calibracion
WINDOW_POINTS = [
    ("desktop_tab", "pestana 'Desktop'"),
    ("ip_configuration_item", "icono 'IP Configuration' (Q si aparece directo)"),
    ("static_radio", "radio button 'Static'"),
    ("close_button", "boton X de la ventana"),
]
SKIP = "skip"


def load_topology(path):
    import json
    if not os.path.exists(path):
        print(f"ERROR: no existe {path}. Corre build.py primero (sin --dry-run).")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: no se pudo leer {path}: {e}")
        sys.exit(1)


def find_device(topology, name):
    devs = topology.get("dispositivos", [])
    for d in devs:
        if str(d.get("nombre", "")).lower() == name.lower():
            return d
    print(f"ERROR: no hay ningun dispositivo llamado '{name}' en topologia_actual.json.")
    print("  Disponibles:", ", ".join(d.get("nombre", "?") for d in devs))
    sys.exit(1)


def calibrate_window(data, only_missing):
    """Captura los puntos de WINDOW_POINTS. 'skip' es un valor valido guardado."""
    print()
    print("  CALIBRACION de los puntos de la ventana emergente")
    print("  1) En Packet Tracer, haz DOBLE CLIC en un dispositivo para abrir su")
    print("     ventana de configuracion. NO la muevas de sitio.")
    print("  2) Marca la pestana 'Desktop' y el boton X (visibles ya).")
    print("  3) Entra a Desktop > IP Configuration a mano y marca 'Static'.")
    print("     Para 'IP Configuration': si aparece directo al pulsar Desktop,")
    print("     pulsa Q para guardarlo como 'skip'.")
    print("-" * 64)
    changed = False
    for key, label in WINDOW_POINTS:
        if only_missing and data.get(key) is not None:
            print(f"  {key:<22} ya calibrado: {data[key]}")
            continue
        p = tci.capture_point(label, data.get(key))
        if p is None:
            if key == "ip_configuration_item":
                data[key] = SKIP
                changed = True
                print(f"    -> '{key}' guardado como '{SKIP}' (no se hara clic)")
            continue
        data[key] = p
        changed = True
    if changed:
        tci.save_coords(data)
    return all(data.get(k) is not None for k, _ in WINDOW_POINTS)


def main():
    ap = argparse.ArgumentParser(
        description="Flujo completo: abrir ventana + escribir IP en un dispositivo.")
    ap.add_argument("name", nargs="?", help="Nombre del dispositivo, ej. PC0")
    ap.add_argument("ip", nargs="?", help="IPv4 Address")
    ap.add_argument("mask", nargs="?", help="Subnet Mask")
    ap.add_argument("gateway", nargs="?", help="Default Gateway")
    ap.add_argument("--topology", default=TOPOLOGY_PATH,
                    help="Registro de topologia (def. topologia_actual.json).")
    ap.add_argument("--calibrate", action="store_true",
                    help="Calibrar los puntos de la ventana y salir.")
    ap.add_argument("--recalibrate", action="store_true",
                    help="Recapturar los puntos de la ventana antes de ejecutar.")
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
    print(f"  Coords : {tci.COORDS_PATH}")

    data = tci.load_coords()

    if args.calibrate:
        done = calibrate_window(data, only_missing=False)
        print("-" * 64)
        print("  Calibracion de ventana completa." if done
              else "  Faltan puntos de ventana por capturar.")
        return

    if not (args.name and args.ip and args.mask and args.gateway):
        ap.error("Indica: NOMBRE IP MASCARA GATEWAY (o usa --calibrate).")

    for label, val in (("IP", args.ip), ("mascara", args.mask), ("gateway", args.gateway)):
        if not tci.valid_ipish(val):
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
    all_keys = [k for k, _ in WINDOW_POINTS] + [k for k, _ in tci.FIELDS]

    if args.dry_run:
        print()
        print("  Plan:")
        print(f"    1. doble clic en ({dx}, {dy})")
        print(f"    2. esperar {args.open_delay}s")
        print(f"    3. clic 'Desktop'        {data.get('desktop_tab', 'SIN CALIBRAR')}")
        ipc = data.get("ip_configuration_item", "SIN CALIBRAR")
        print(f"    4. clic 'IP Configuration' {ipc}"
              + ("  (se salta)" if ipc == SKIP else ""))
        print(f"    5. clic 'Static'         {data.get('static_radio', 'SIN CALIBRAR')}")
        for i, (key, lbl) in enumerate(tci.FIELDS, start=6):
            print(f"    {i}. clic {lbl:<16} {data.get(key, 'SIN CALIBRAR')}"
                  f"  -> Ctrl+A+Supr -> '{values[key]}'")
        print(f"    9. clic X (cerrar)       {data.get('close_button', 'SIN CALIBRAR')}")
        print()
        print("  DRY-RUN: no se movera el mouse.")
        print("=" * 64)
        return

    if args.recalibrate:
        calibrate_window(data, only_missing=False)

    missing = [k for k in all_keys if data.get(k) is None]
    if missing:
        print(f"  Faltan puntos: {', '.join(missing)}")
        if any(k in missing for k, _ in tci.FIELDS):
            print("  Los campos IPv4/Mascara/Gateway se calibran con:")
            print("     python test_configure_ip.py --calibrate")
        if any(k in missing for k, _ in WINDOW_POINTS):
            if not calibrate_window(data, only_missing=True):
                print("  Calibracion de ventana incompleta. Aborta.")
                sys.exit(1)
        missing = [k for k in all_keys if data.get(k) is None]
        if missing:
            print(f"  Siguen faltando: {', '.join(missing)}. Aborta.")
            sys.exit(1)

    print()
    print("  Plan: doble clic dispositivo -> Desktop -> IP Configuration -> Static")
    print("        -> escribir 3 campos -> cerrar")
    print()
    print("  Pon el foco en Packet Tracer. La ventana del dispositivo se abrira sola.")
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
        pyautogui.doubleClick(dx, dy)
        time.sleep(args.open_delay)

        pyautogui.click(*data["desktop_tab"])
        time.sleep(args.tab_delay)

        if data.get("ip_configuration_item") not in (None, SKIP):
            pyautogui.click(*data["ip_configuration_item"])
            time.sleep(args.tab_delay)

        pyautogui.click(*data["static_radio"])
        time.sleep(p)

        for key, _ in tci.FIELDS:
            tci.type_into(data[key], values[key], p)

        pyautogui.click(*data["close_button"])
        time.sleep(p)

        w, h = pyautogui.size()
        pyautogui.moveTo(w // 2, h // 2)
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
        print("    - Se abrio la ventana del dispositivo correcto?")
        print("    - Quedo en 'Static' y los 3 campos correctos?")
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
