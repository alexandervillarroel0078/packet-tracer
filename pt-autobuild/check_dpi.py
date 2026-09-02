"""
check_dpi.py - Comprueba que pyautogui trabaja en pixeles fisicos reales.

Ejecuta:
    python check_dpi.py            # informe y sale
    python check_dpi.py --watch    # ademas muestra la posicion del raton en vivo

El informe compara pyautogui.size() con la resolucion fisica real del monitor:
si coinciden, la DPI awareness surtio efecto y locateOnScreen / los clics caen
donde ves los iconos, aunque Windows este a 125 %.

Con --watch, lleva el cursor a la esquina INFERIOR DERECHA: debe leer un valor
cercano a la resolucion fisica (no a una resolucion "logica" menor).
"""

import argparse
import sys
import time

import dpi_aware  # noqa: F401  antes de pyautogui
import pyautogui

try:
    import msvcrt
except ImportError:
    msvcrt = None


def report():
    print("=" * 64)
    print("  COMPROBACION DE DPI / COORDENADAS")
    print("=" * 64)
    print(f"  Via aplicada        : {dpi_aware.STATUS}")
    print(f"  Resolucion fisica   : {dpi_aware.physical_size()}")
    print(f"  pyautogui.size()    : {tuple(pyautogui.size())}")
    ok, msg = dpi_aware.verify()
    print(f"  Resultado           : {msg}")
    print("-" * 64)
    if ok:
        print("  Las coordenadas de pyautogui = pixeles fisicos. locateOnScreen y")
        print("  los clics deberian caer donde ves los iconos.")
    else:
        print("  Sigue habiendo desfase. Revisa que dpi_aware se importa ANTES que")
        print("  pyautogui y que no hay un manifiesto/arranque que fije otra cosa.")
    print("-" * 64)
    return ok


def watch():
    if msvcrt is None:
        print("  --watch no disponible: no es Windows.")
        return
    print("  Mueve el raton. Esquina INFERIOR DERECHA ~= resolucion fisica.")
    print("  Pulsa Q para salir (o Ctrl+C).")
    while msvcrt.kbhit():
        msvcrt.getch()
    try:
        while True:
            x, y = pyautogui.position()
            sys.stdout.write(f"\r  raton: x={x:>5}  y={y:>5}   ")
            sys.stdout.flush()
            if msvcrt.kbhit() and msvcrt.getch() in (b"q", b"Q", b"\x1b"):
                break
            time.sleep(0.05)
    except (KeyboardInterrupt, OSError):
        pass
    print()


def main():
    ap = argparse.ArgumentParser(description="Comprueba la DPI awareness de pyautogui.")
    ap.add_argument("--watch", action="store_true",
                    help="Muestra la posicion del raton en vivo tras el informe.")
    args = ap.parse_args()

    report()
    if args.watch:
        watch()


if __name__ == "__main__":
    main()
