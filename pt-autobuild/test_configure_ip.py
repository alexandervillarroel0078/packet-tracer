"""
test_configure_ip.py - Prueba de escritura en la ventana de configuracion IP.

Valida el paso mas basico antes de conectar esto con datos reales de topologia:
escribir IP / mascara / gateway en los campos de

    (ventana de un PC)  Desktop  >  IP Configuration

Este script NO abre la ventana ni navega a la pestana: das por hecho que TU
ya tienes abierta manualmente la ventana de configuracion de un PC en Packet
Tracer, con "IP Configuration" (modo Static) visible. El script solo hace
clic en cada campo y escribe.

Necesita 3 puntos, calibrados con el metodo manual de siempre (mueve el mouse
y pulsa ESPACIO). Se guardan en su PROPIO archivo, ip_config_coords.json,
para no mezclarlos con coords.json (que es del lienzo principal):

    ipv4_address     campo "IPv4 Address"
    subnet_mask      campo "Subnet Mask"
    default_gateway  campo "Default Gateway"

Uso:
    python test_configure_ip.py 192.168.10.10 255.255.255.0 192.168.10.1
    python test_configure_ip.py 192.168.10.10 255.255.255.0 192.168.10.1 --dry-run
    python test_configure_ip.py ... --recalibrate     # recapturar los 3 puntos
    python test_configure_ip.py --calibrate           # solo calibrar y salir

Secuencia (tras cuenta regresiva de 5 s):
    clic IPv4 Address  -> Ctrl+A + Supr -> escribir IP
    clic Subnet Mask   -> Ctrl+A + Supr -> escribir mascara
    clic Default Gateway -> Ctrl+A + Supr -> escribir gateway

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre clics.
"""

import argparse
import json
import os
import re
import sys
import time

import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui (fija DPI awareness)

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala:  pip install -r requirements.txt")
    sys.exit(1)

try:
    import msvcrt  # captura manual de puntos (Windows)
except ImportError:
    msvcrt = None


HERE = os.path.dirname(os.path.abspath(__file__))
COORDS_PATH = os.path.join(HERE, "ip_config_coords.json")

# clave en el JSON -> etiqueta legible, en el orden en que se escriben
FIELDS = [
    ("ipv4_address", "IPv4 Address"),
    ("subnet_mask", "Subnet Mask"),
    ("default_gateway", "Default Gateway"),
]

_DOTTED_QUAD = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


# --- datos ------------------------------------------------------------
def load_coords():
    if not os.path.exists(COORDS_PATH):
        return {}
    try:
        with open(COORDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        print("  Aviso: ip_config_coords.json existe pero no se pudo leer; se ignora.")
        return {}


def save_coords(data):
    """Escribe ip_config_coords.json de forma atomica y verifica que quedo."""
    data["screen_size"] = list(pyautogui.size())
    tmp = COORDS_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, COORDS_PATH)
    except OSError as e:
        print(f"  ERROR al guardar ip_config_coords.json: {type(e).__name__}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
    ok = os.path.exists(COORDS_PATH)
    print(f"  {'OK' if ok else 'ERROR'}: ip_config_coords.json "
          f"{'guardado y verificado' if ok else 'NO se escribio'}.")
    return ok


# --- captura manual de un punto -------------------------------------
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


def calibrate(data, only_missing):
    """
    Captura los 3 puntos. Si only_missing, salta los que ya existen.
    Devuelve True si al final estan los 3.
    """
    print()
    print("  CALIBRACION de ip_config_coords.json")
    print("  Ten YA abierta en Packet Tracer la ventana del PC con 'IP Configuration'")
    print("  visible (modo Static). Vas a marcar el centro de cada campo de texto.")
    print("-" * 64)
    changed = False
    for key, label in FIELDS:
        if only_missing and data.get(key) is not None:
            print(f"  {label:<16} ya calibrado: {data[key]}")
            continue
        p = capture_point(label, data.get(key))
        if p is not None:
            data[key] = p
            changed = True
    if changed:
        save_coords(data)
    return all(data.get(k) is not None for k, _ in FIELDS)


def valid_ipish(s):
    if not _DOTTED_QUAD.match(s):
        return False
    return all(0 <= int(o) <= 255 for o in s.split("."))


# --- ejecucion ------------------------------------------------------
def type_into(point, value, pause):
    pyautogui.click(point[0], point[1])
    time.sleep(pause)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    pyautogui.press("delete")
    time.sleep(0.15)
    pyautogui.write(str(value), interval=0.05)
    time.sleep(pause)


def main():
    ap = argparse.ArgumentParser(
        description="Prueba de escritura de IP/mascara/gateway en Packet Tracer.")
    ap.add_argument("ip", nargs="?", help="IPv4 Address, ej. 192.168.10.10")
    ap.add_argument("mask", nargs="?", help="Subnet Mask, ej. 255.255.255.0")
    ap.add_argument("gateway", nargs="?", help="Default Gateway, ej. 192.168.10.1")
    ap.add_argument("--calibrate", action="store_true",
                    help="Solo calibrar los 3 puntos y salir.")
    ap.add_argument("--recalibrate", action="store_true",
                    help="Volver a capturar los 3 puntos aunque ya existan.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Imprime el plan sin mover el mouse.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre clics en segundos (def. 0.4).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    print("=" * 64)
    print("  test_configure_ip.py :: escribir IP en la ventana de config")
    print("=" * 64)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")
    print(f"  Coords: {COORDS_PATH}")

    data = load_coords()

    if args.calibrate:
        done = calibrate(data, only_missing=False)
        print("-" * 64)
        print("  Calibracion completa." if done else "  Faltan puntos por capturar.")
        return

    if not (args.ip and args.mask and args.gateway):
        ap.error("Indica IP, mascara y gateway (o usa --calibrate).")

    for name, val in (("IP", args.ip), ("mascara", args.mask), ("gateway", args.gateway)):
        if not valid_ipish(val):
            ap.error(f"{name} '{val}' no parece un IPv4 valido (x.x.x.x, 0-255).")

    values = {"ipv4_address": args.ip, "subnet_mask": args.mask,
              "default_gateway": args.gateway}

    if args.dry_run:
        print()
        print("  Plan:")
        for i, (key, label) in enumerate(FIELDS, 1):
            pt = data.get(key, "SIN CALIBRAR")
            print(f"    {i}. clic {label:<16} {pt}  -> Ctrl+A+Supr -> '{values[key]}'")
        print()
        print("  DRY-RUN: no se movera el mouse.")
        print("=" * 64)
        return

    if args.recalibrate:
        calibrate(data, only_missing=False)
    missing = [lbl for k, lbl in FIELDS if data.get(k) is None]
    if missing:
        print(f"  Faltan puntos: {', '.join(missing)}. Vamos a calibrarlos.")
        if not calibrate(data, only_missing=True):
            print("  No se completo la calibracion. Aborta.")
            sys.exit(1)

    print()
    print("  Plan:")
    for i, (key, label) in enumerate(FIELDS, 1):
        print(f"    {i}. clic {label:<16} {data[key]}  -> Ctrl+A+Supr -> '{values[key]}'")
    print()

    print("  Asegurate de que la ventana 'IP Configuration' del PC esta visible")
    print("  y en modo Static ANTES de que acabe la cuenta.")
    for i in range(max(0, args.countdown), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...  (pon el foco en Packet Tracer)   ")
        sys.stdout.flush()
        time.sleep(1)
    print("\r  Ejecutando...                                        ")

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    done = False
    try:
        for key, _ in FIELDS:
            type_into(data[key], values[key], args.pause)
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
        print(f"  IPv4 Address    -> {args.ip}")
        print(f"  Subnet Mask     -> {args.mask}")
        print(f"  Default Gateway -> {args.gateway}")
        print("  Revisa en Packet Tracer que los 3 campos quedaron correctos.")
        print("  Si algun campo quedo mal / con texto pegado: recalibra ese punto")
        print("  con  python test_configure_ip.py --recalibrate")
    else:
        print("  Ejecucion abortada; nada garantizado.")
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
