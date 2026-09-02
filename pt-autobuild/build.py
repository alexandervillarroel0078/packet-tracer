"""
build.py - Colocacion automatica de dispositivos en Cisco Packet Tracer.

Lee una topologia simple en texto, calcula un layout en cuadricula y ejecuta
la secuencia de clics necesaria para colocar cada dispositivo, usando las
coordenadas capturadas con calibrate.py (coords.json).

Uso:
    python build.py "4 routers, 4 switches, 8 PCs"
    python build.py --file topologia.txt
    python build.py "2 routers, 3 switches, 12 pcs" --dry-run

Opciones:
    --file RUTA     Lee la descripcion de la topologia desde un archivo de texto.
    --dry-run       Calcula e imprime el plan SIN mover el mouse ni hacer clics.
    --pause SEG     Pausa entre clics (def. 0.4). Subelo si Packet Tracer va lento.
    --countdown N   Segundos de cuenta regresiva antes de empezar (def. 5).

Alcance (a proposito limitado):
    - Solo coloca dispositivos genericos. No cablea. No configura. No renombra.
    - No lee la pantalla: es "a ciegas", confia en coords.json.

Seguridad:
    - Cuenta regresiva antes de empezar para que cambies el foco a Packet Tracer.
    - Failsafe de pyautogui activo: lleva el mouse a la esquina superior
      izquierda de la pantalla para abortar de inmediato.
    - Pausa configurable entre cada clic.
"""

import argparse
import json
import math
import os
import re
import sys
import time

import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui (fija DPI awareness)

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala las dependencias con:")
    print("    pip install -r requirements.txt")
    sys.exit(1)


HERE = os.path.dirname(os.path.abspath(__file__))
COORDS_PATH = os.path.join(HERE, "coords.json")

# --- Parametros de layout (pixeles) -----------------------------------------
MIN_DX = 55          # separacion horizontal minima recomendada entre dispositivos
ROW_GAP_MIN = 80     # separacion vertical minima entre filas (routers/switches/pcs)
ROW_GAP_FRAC = 0.18  # o esta fraccion del alto util, lo que sea mayor
PC_DX = 55           # separacion horizontal entre PCs de un mismo grupo
PC_DY = 55           # separacion vertical entre PCs de un mismo grupo

# type -> (clave en coords["categories"], clave en coords["models"])
DEVICE_MAP = {
    "router": ("router", "router"),
    "switch": ("switch", "switch"),
    "pc": ("end_devices", "pc"),
}

# sinonimos aceptados en el texto de topologia -> tipo canonico
SYNONYMS = {
    "router": "router", "routers": "router", "r": "router",
    "switch": "switch", "switches": "switch", "sw": "switch", "s": "switch",
    "pc": "pc", "pcs": "pc", "host": "pc", "hosts": "pc",
    "computer": "pc", "computers": "pc", "computadora": "pc", "computadoras": "pc",
    "enddevice": "pc", "enddevices": "pc",
}


# --- Parseo de topologia ----------------------------------------------------
def parse_topology(text):
    """
    Extrae conteos de una descripcion libre.
    Reconoce patrones tipo '<numero> <tipo>' en cualquier orden, separados por
    comas, saltos de linea, 'y' / 'and'. Ejemplos validos:
        '4 routers, 4 switches, 8 PCs'
        '4x router\n4x switch\n8x pc'
    Devuelve dict {tipo_canonico: cantidad} solo con los tipos presentes.
    """
    counts = {}
    unknown = set()
    # comentarios estilo '#'
    text = re.sub(r"#.*", "", text)
    for num, word in re.findall(r"(\d+)\s*x?\s*([A-Za-z_]+)", text):
        key = word.lower().replace("_", "")
        canonical = SYNONYMS.get(key)
        if canonical is None:
            unknown.add(word)
            continue
        counts[canonical] = counts.get(canonical, 0) + int(num)
    for w in sorted(unknown):
        print(f"  Aviso: termino no reconocido en la topologia: '{w}' (ignorado)")
    return counts


# --- Carga de coordenadas -------------------------------------------------
def load_coords():
    if not os.path.exists(COORDS_PATH):
        print(f"ERROR: no existe {COORDS_PATH}")
        print("Ejecuta primero:  python calibrate.py")
        sys.exit(1)
    with open(COORDS_PATH, "r", encoding="utf-8") as f:
        coords = json.load(f)

    required = {
        ("categories", "router"), ("categories", "switch"),
        ("categories", "end_devices"),
        ("models", "router"), ("models", "switch"), ("models", "pc"),
        ("canvas", "top_left"), ("canvas", "bottom_right"),
    }
    missing = [f"{s}.{k}" for s, k in sorted(required)
               if coords.get(s, {}).get(k) is None]
    if missing:
        print("ERROR: faltan coordenadas en coords.json:")
        for m in missing:
            print(f"  - {m}")
        print("Vuelve a ejecutar calibrate.py para capturarlas.")
        sys.exit(1)

    saved = coords.get("screen_size")
    current = list(pyautogui.size())
    if saved and saved != current:
        print(f"  Aviso: la resolucion actual {tuple(current)} no coincide con la")
        print(f"  de la calibracion {tuple(saved)}. Las coordenadas pueden fallar.")
    return coords


# --- Calculo de layout --------------------------------------------------
def spread(n, xa, xb):
    """n posiciones x repartidas uniformemente en [xa, xb] con medio paso de margen."""
    if n <= 0:
        return []
    if n == 1:
        return [round((xa + xb) / 2)]
    step = (xb - xa) / n
    return [round(xa + step * (i + 0.5)) for i in range(n)]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def compute_layout(counts, coords):
    """
    Devuelve (placements, warnings) donde placements es una lista ordenada de
    dicts {type, x, y} en el orden en que se colocaran.
    Disposicion: routers en una fila arriba, switches en la fila siguiente,
    y los PCs repartidos en columnas debajo de cada switch (o en cuadricula
    si no hay switches).
    """
    x0, y0 = coords["canvas"]["top_left"]
    x1, y1 = coords["canvas"]["bottom_right"]
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)

    usable_h = y1 - y0
    row_gap = max(ROW_GAP_MIN, usable_h * ROW_GAP_FRAC)

    n_r = counts.get("router", 0)
    n_s = counts.get("switch", 0)
    n_p = counts.get("pc", 0)

    warnings = []
    placements = []

    cursor_y = y0
    router_y = switch_y = None
    if n_r > 0:
        router_y = round(cursor_y)
        cursor_y += row_gap
    if n_s > 0:
        switch_y = round(cursor_y)
        cursor_y += row_gap
    pc_y_start = round(cursor_y)

    # Routers
    router_xs = spread(n_r, x0, x1)
    for x in router_xs:
        placements.append({"type": "router", "x": clamp(x, x0, x1), "y": router_y})
    if n_r > 1 and (x1 - x0) / n_r < MIN_DX:
        warnings.append(f"{n_r} routers en {x1 - x0}px: quedan a "
                        f"{round((x1 - x0) / n_r)}px (< {MIN_DX}px), pueden solaparse.")

    # Switches
    switch_xs = spread(n_s, x0, x1)
    for x in switch_xs:
        placements.append({"type": "switch", "x": clamp(x, x0, x1), "y": switch_y})
    if n_s > 1 and (x1 - x0) / n_s < MIN_DX:
        warnings.append(f"{n_s} switches en {x1 - x0}px: quedan a "
                        f"{round((x1 - x0) / n_s)}px (< {MIN_DX}px), pueden solaparse.")

    # PCs
    if n_p > 0:
        avail_v = max(PC_DY, y1 - pc_y_start)
        rows_per_col = max(1, int(avail_v // PC_DY))

        if n_s > 0:
            base, extra = divmod(n_p, n_s)
            groups = [base + (1 if i < extra else 0) for i in range(n_s)]
            for i, count in enumerate(groups):
                sx = switch_xs[i]
                for k in range(count):
                    col = k // rows_per_col
                    row = k % rows_per_col
                    # columnas centradas alrededor de sx
                    n_cols = math.ceil(count / rows_per_col)
                    x = sx + (col - (n_cols - 1) / 2) * PC_DX
                    y = pc_y_start + row * PC_DY
                    placements.append({
                        "type": "pc",
                        "x": round(clamp(x, x0, x1)),
                        "y": round(clamp(y, y0, y1)),
                    })
            max_group = max(groups) if groups else 0
            if max_group > rows_per_col * 3:
                warnings.append(f"Hasta {max_group} PCs por switch: el area no da "
                                f"para tantas filas/columnas, revisa el resultado.")
        else:
            # sin switches: cuadricula simple en toda el area de PCs
            cols = max(1, int((x1 - x0) // PC_DX))
            grid_xs = spread(min(cols, n_p), x0, x1)
            for k in range(n_p):
                col = k % cols
                row = k // cols
                x = grid_xs[col] if col < len(grid_xs) else x0 + col * PC_DX
                y = pc_y_start + row * PC_DY
                placements.append({
                    "type": "pc",
                    "x": round(clamp(x, x0, x1)),
                    "y": round(clamp(y, y0, y1)),
                })

    return placements, warnings


# --- Ejecucion --------------------------------------------------------
def countdown(seconds):
    print()
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...  (cambia el foco a Packet Tracer)   ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r  Colocando dispositivos...                                     \n")
    sys.stdout.flush()


def place_device(coords, dev_type, x, y, pause):
    cat_key, model_key = DEVICE_MAP[dev_type]
    cx, cy = coords["categories"][cat_key]
    mx, my = coords["models"][model_key]

    pyautogui.click(cx, cy)
    time.sleep(pause)
    pyautogui.click(mx, my)
    time.sleep(pause)
    pyautogui.click(x, y)
    time.sleep(pause)


def print_plan(counts, placements, warnings, dry_run):
    print("=" * 70)
    print("  pt-autobuild :: PLAN DE COLOCACION")
    print("=" * 70)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    _dpi_ok, _dpi_msg = dpi_aware.verify()
    print(f"  {'' if _dpi_ok else '[!] '}{_dpi_msg}")
    print("-" * 70)
    if not counts:
        print("  Topologia vacia: nada que colocar.")
        return
    for t in ("router", "switch", "pc"):
        if counts.get(t):
            print(f"  {t:<8} x {counts[t]}")
    print(f"  Total: {sum(counts.values())} dispositivos")
    print("-" * 70)
    for idx, p in enumerate(placements, 1):
        print(f"  {idx:>3}. {p['type']:<7} -> ({p['x']:>5}, {p['y']:>5})")
    if warnings:
        print("-" * 70)
        for w in warnings:
            print(f"  [!] {w}")
    if dry_run:
        print("-" * 70)
        print("  DRY-RUN: no se movera el mouse.")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="Coloca dispositivos en Packet Tracer.")
    ap.add_argument("topology", nargs="?", default=None,
                    help='Ej: "4 routers, 4 switches, 8 PCs"')
    ap.add_argument("--file", help="Lee la topologia desde un archivo de texto.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Calcula e imprime el plan sin hacer clics.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre clics en segundos (def. 0.4).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.topology:
        text = args.topology
    else:
        ap.error("Indica una topologia como argumento o usa --file.")

    counts = parse_topology(text)
    counts = {t: n for t, n in counts.items() if n > 0}
    if not counts:
        print("No se reconocio ningun dispositivo en la topologia.")
        sys.exit(1)

    coords = load_coords()
    placements, warnings = compute_layout(counts, coords)

    print_plan(counts, placements, warnings, args.dry_run)

    if args.dry_run:
        return

    pyautogui.FAILSAFE = True  # esquina sup. izq. aborta
    pyautogui.PAUSE = 0.0      # controlamos las pausas manualmente

    countdown(max(0, args.countdown))

    attempted = {"router": 0, "switch": 0, "pc": 0}
    placed_ok = 0
    aborted = False
    try:
        for p in placements:
            place_device(coords, p["type"], p["x"], p["y"], args.pause)
            attempted[p["type"]] += 1
            placed_ok += 1
    except pyautogui.FailSafeException:
        aborted = True
        print("\n  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except KeyboardInterrupt:
        aborted = True
        print("\n  Interrumpido por el usuario.")

    print()
    print("=" * 70)
    print("  RESUMEN")
    print("=" * 70)
    for t in ("router", "switch", "pc"):
        if counts.get(t):
            print(f"  {t:<8}: {attempted[t]} / {counts[t]} colocados")
    print("-" * 70)
    print(f"  Total intentado: {placed_ok} / {len(placements)}")
    if aborted:
        print("  Ejecucion incompleta (abortada).")
    print("  Recuerda: los cables se conectan manualmente.")
    print("=" * 70)


if __name__ == "__main__":
    main()
