"""
build.py - Colocacion automatica de dispositivos en Cisco Packet Tracer.

Lee una topologia simple en texto, resuelve cada modelo contra device_catalog.json,
calcula un layout en cuadricula y coloca cada dispositivo con el flujo por
BUSCADOR (el buscador de Packet Tracer es global y siempre visible, no hace
falta abrir ninguna categoria):

    1. clic en search_field                (coords.json)
    2. Ctrl+A + Supr                        (limpiar texto previo)
    3. escribir el nombre del modelo        (filtra en vivo, sin Enter)
    4. esperar --filter-delay a que filtre
    5. clic en filtered_result             (coords.json, posicion fija unica)
    6. clic en la posicion calculada del lienzo

Uso:
    python build.py "4 routers, 4 switches, 8 PCs" --dry-run
    python build.py "3 routers modelo 4331, 2 switches modelo 2960, 5 PC, 1 tablet"
    python build.py --file topologia.txt
    python build.py --list-models

Sintaxis de topologia (clausulas separadas por comas o saltos de linea):
    <n> <tipo> [modelo <M>]
      <tipo>  : router(s), switch(es), pc(s), laptop, tablet, server, smartphone,
                "end device(s)"
      modelo  : opcional; si falta se usa el default de device_catalog.json.
                'pc', 'tablet', etc. ya implican su modelo.
    Ejemplos: "3 routers modelo 4331"   "2 switches"   "5 PC"   "1 tablet"
              "4 routers, 4 switches, 8 PCs"   (sigue valiendo; usa defaults)

Opciones:
    --file RUTA        Topologia desde archivo de texto (acepta '#' de comentario).
    --catalog RUTA     Catalogo alternativo (def. device_catalog.json).
    --dry-run          Calcula e imprime el plan SIN mover el mouse.
    --list-models      Imprime el catalogo y sale.
    --pause SEG        Pausa entre clics (def. 0.4).
    --filter-delay SEG Espera tras escribir, antes de clicar el resultado (def. 0.4).
    --countdown N      Cuenta regresiva antes de empezar (def. 5).

Alcance (a proposito limitado):
    - Solo coloca dispositivos. No cablea. No configura. No renombra.
    - No lee la pantalla: es "a ciegas", confia en coords.json y en el catalogo.

Seguridad:
    - Cuenta regresiva antes de empezar (cambia el foco a Packet Tracer).
    - Failsafe de pyautogui: mouse a la esquina superior izquierda = aborta.
    - Pausa configurable entre cada clic.
"""

import argparse
import datetime
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
CATALOG_PATH = os.path.join(HERE, "device_catalog.json")

# --- Parametros de layout (pixeles) --------------------------------------
MIN_DX = 55          # separacion horizontal minima recomendada entre dispositivos
ROW_GAP_MIN = 80     # separacion vertical minima entre filas
ROW_GAP_FRAC = 0.18  # o esta fraccion del alto util, lo que sea mayor
END_DX = 55          # separacion horizontal entre end devices de un grupo
END_DY = 55          # separacion vertical entre end devices de un grupo

# categoria canonica -> (clave en el catalogo, etiqueta legible)
CAT_INFO = {
    "router":     ("routers", "router"),
    "switch":     ("switches", "switch"),
    "end_device": ("end_devices", "end device"),
}
CAT_ORDER = ("router", "switch", "end_device")

# nombre base con el que Packet Tracer nombra cada dispositivo por defecto.
# El contador es por nombre base y arranca en 0 (Router0, Router1, Switch0, PC0...).
# Nota: en Packet Tracer la tablet real aparece como "Tablet PC0"; aqui se usa
# "Tablet0" por simplicidad y consistencia con el resto.
PT_BASE_NAME = {
    "router": "Router",
    "switch": "Switch",
    "PC": "PC",
    "Laptop": "Laptop",
    "Tablet": "Tablet",
    "Server": "Server",
    "Smartphone": "Smartphone",
}

# palabra en el texto -> (categoria canonica, modelo implicito o None)
WORD_MAP = {
    "router": ("router", None), "routers": ("router", None), "r": ("router", None),
    "switch": ("switch", None), "switches": ("switch", None),
    "sw": ("switch", None),
    "pc": ("end_device", "PC"), "pcs": ("end_device", "PC"),
    "host": ("end_device", "PC"), "hosts": ("end_device", "PC"),
    "computer": ("end_device", "PC"), "computers": ("end_device", "PC"),
    "laptop": ("end_device", "Laptop"), "laptops": ("end_device", "Laptop"),
    "tablet": ("end_device", "Tablet"), "tablets": ("end_device", "Tablet"),
    "server": ("end_device", "Server"), "servers": ("end_device", "Server"),
    "smartphone": ("end_device", "Smartphone"),
    "smartphones": ("end_device", "Smartphone"),
    "phone": ("end_device", "Smartphone"), "phones": ("end_device", "Smartphone"),
    "enddevice": ("end_device", None), "enddevices": ("end_device", None),
}


# --- Catalogo -----------------------------------------------------------
def load_catalog(path):
    if not os.path.exists(path):
        print(f"ERROR: no existe el catalogo {path}")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            cat = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: no se pudo leer {path}: {e}")
        sys.exit(1)

    for key in ("routers", "switches", "end_devices"):
        if not isinstance(cat.get(key), list) or not cat[key]:
            print(f"ERROR: el catalogo debe tener una lista no vacia en '{key}'.")
            sys.exit(1)
    cat.setdefault("defaults", {})
    return cat


def resolve_model(category, candidate, catalog, errors):
    """
    category  : 'router' | 'switch' | 'end_device'
    candidate : modelo pedido (explicito o implicito) o None -> usar default
    Devuelve el nombre EXACTO del catalogo, o None si no existe (y apila error).
    """
    cat_key, label = CAT_INFO[category]
    models = catalog[cat_key]
    lower_map = {m.lower(): m for m in models}

    if candidate is None:
        candidate = catalog["defaults"].get(cat_key)
        if not candidate:
            errors.append(f"No hay modelo por defecto para '{cat_key}' en el catalogo "
                          f"y no especificaste 'modelo <X>'.")
            return None

    canon = lower_map.get(str(candidate).lower())
    if canon is None:
        disponibles = ", ".join(models)
        errors.append(f"Modelo '{candidate}' no esta en el catalogo para {label}s. "
                      f"Disponibles: {disponibles}")
        return None
    return canon


# --- Parseo de topologia ------------------------------------------------
def parse_topology(text):
    """
    Devuelve (groups, warnings) donde cada group es
        {"category": str, "model": str|None, "count": int, "word": str}
    'model' es el modelo explicito o implicito; None => usar default del catalogo.
    """
    warnings = []
    groups = []

    text = re.sub(r"#.*", "", text)                       # comentarios
    text = re.sub(r"end[\s\-]*devices?", "enddevices", text, flags=re.I)  # "end device"

    clauses = re.split(r"[,\n;]+|\s+\by\b\s+|\s+\band\b\s+", text, flags=re.I)
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        m = re.match(r"(\d+)\s*x?\s*([A-Za-z]+)\s*(.*)$", clause)
        if not m:
            warnings.append(f"clausula no reconocida: '{clause}' (ignorada)")
            continue
        num = int(m.group(1))
        word = m.group(2).lower()
        rest = m.group(3).strip()

        if word not in WORD_MAP:
            warnings.append(f"tipo no reconocido: '{m.group(2)}' en '{clause}' (ignorado)")
            continue
        category, implied = WORD_MAP[word]

        model = None
        if rest:
            rm = re.match(r"(?:modelo|model|mod)\s+(.+)$", rest, flags=re.I)
            model = (rm.group(1) if rm else rest).split()[0]

        if model and implied and model.lower() != implied.lower():
            warnings.append(f"'{word}' suele ser '{implied}', pero pediste modelo "
                            f"'{model}'; se usara '{model}'.")

        if num <= 0:
            continue
        groups.append({"category": category,
                       "model": model or implied,
                       "count": num,
                       "word": word})
    return groups, warnings


# --- Carga de coordenadas ------------------------------------------------
def load_coords():
    if not os.path.exists(COORDS_PATH):
        print(f"ERROR: no existe {COORDS_PATH}")
        print("Ejecuta primero:  python calibrate.py")
        sys.exit(1)
    with open(COORDS_PATH, "r", encoding="utf-8") as f:
        coords = json.load(f)

    missing = []
    if coords.get("search_field") is None:
        missing.append("search_field")
    if coords.get("filtered_result") is None:
        missing.append("filtered_result")
    for k in ("top_left", "bottom_right"):
        if coords.get("canvas", {}).get(k) is None:
            missing.append(f"canvas.{k}")
    if missing:
        print("ERROR: faltan coordenadas en coords.json:")
        for mkey in missing:
            print(f"  - {mkey}")
        print("Ejecuta:  python calibrate.py")
        print("(o para search_field/filtered_result:  python test_place.py <modelo> --save)")
        sys.exit(1)

    saved = coords.get("screen_size")
    current = list(pyautogui.size())
    if saved and saved != current:
        print(f"  Aviso: la resolucion actual {tuple(current)} no coincide con la de")
        print(f"  la calibracion {tuple(saved)}. Las coordenadas pueden fallar.")
    return coords


# --- Calculo de layout -------------------------------------------------
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


def compute_layout(resolved, coords):
    """
    resolved: lista de {category, model, count}.
    Devuelve (placements, warnings). placements = lista ordenada de
        {category, model, x, y}
    Disposicion: routers en la fila de arriba, switches en la siguiente, y los
    end devices repartidos en columnas debajo de cada switch (o en cuadricula
    si no hay switches). Varios grupos de la misma categoria se concatenan en
    la misma fila, en el orden en que aparecen.
    """
    x0, y0 = coords["canvas"]["top_left"]
    x1, y1 = coords["canvas"]["bottom_right"]
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)

    usable_h = y1 - y0
    row_gap = max(ROW_GAP_MIN, usable_h * ROW_GAP_FRAC)

    by_cat = {"router": [], "switch": [], "end_device": []}
    for r in resolved:
        by_cat[r["category"]].extend([r["model"]] * r["count"])

    routers, switches, ends = by_cat["router"], by_cat["switch"], by_cat["end_device"]
    n_r, n_s, n_e = len(routers), len(switches), len(ends)

    warnings = []
    placements = []

    cursor_y = y0
    router_y = switch_y = None
    if n_r:
        router_y = round(cursor_y)
        cursor_y += row_gap
    if n_s:
        switch_y = round(cursor_y)
        cursor_y += row_gap
    end_y_start = round(cursor_y)

    # Routers
    for x, model in zip(spread(n_r, x0, x1), routers):
        placements.append({"category": "router", "model": model,
                           "x": clamp(x, x0, x1), "y": router_y})
    if n_r > 1 and (x1 - x0) / n_r < MIN_DX:
        warnings.append(f"{n_r} routers en {x1 - x0}px: ~{round((x1 - x0) / n_r)}px "
                        f"cada uno (< {MIN_DX}), pueden solaparse.")

    # Switches
    switch_xs = spread(n_s, x0, x1)
    for x, model in zip(switch_xs, switches):
        placements.append({"category": "switch", "model": model,
                           "x": clamp(x, x0, x1), "y": switch_y})
    if n_s > 1 and (x1 - x0) / n_s < MIN_DX:
        warnings.append(f"{n_s} switches en {x1 - x0}px: ~{round((x1 - x0) / n_s)}px "
                        f"cada uno (< {MIN_DX}), pueden solaparse.")

    # End devices
    if n_e:
        avail_v = max(END_DY, y1 - end_y_start)
        rows_per_col = max(1, int(avail_v // END_DY))

        if n_s:
            base, extra = divmod(n_e, n_s)
            per_switch = [base + (1 if i < extra else 0) for i in range(n_s)]
            ei = 0
            for i, cnt in enumerate(per_switch):
                sx = switch_xs[i]
                n_cols = math.ceil(cnt / rows_per_col) if cnt else 1
                for k in range(cnt):
                    col = k // rows_per_col
                    row = k % rows_per_col
                    x = sx + (col - (n_cols - 1) / 2) * END_DX
                    y = end_y_start + row * END_DY
                    placements.append({"category": "end_device", "model": ends[ei],
                                       "x": round(clamp(x, x0, x1)),
                                       "y": round(clamp(y, y0, y1))})
                    ei += 1
            if per_switch and max(per_switch) > rows_per_col * 3:
                warnings.append(f"Hasta {max(per_switch)} end devices por switch: el "
                                f"area puede no dar, revisa el resultado.")
        else:
            cols = max(1, int((x1 - x0) // END_DX))
            grid_xs = spread(min(cols, n_e), x0, x1)
            for k, model in enumerate(ends):
                col = k % cols
                row = k // cols
                x = grid_xs[col] if col < len(grid_xs) else x0 + col * END_DX
                y = end_y_start + row * END_DY
                placements.append({"category": "end_device", "model": model,
                                   "x": round(clamp(x, x0, x1)),
                                   "y": round(clamp(y, y0, y1))})

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


def place_device(coords, model, x, y, pause, filter_delay):
    sfx, sfy = coords["search_field"]
    frx, fry = coords["filtered_result"]

    pyautogui.click(sfx, sfy)          # 1. foco en el buscador (y desarma colocacion previa)
    time.sleep(pause)
    pyautogui.hotkey("ctrl", "a")      # 2. seleccionar texto previo
    time.sleep(0.15)
    pyautogui.press("delete")          #    borrarlo
    time.sleep(0.15)
    pyautogui.write(str(model), interval=0.05)  # 3. escribir el modelo
    time.sleep(filter_delay)           # 4. dejar que filtre
    pyautogui.click(frx, fry)          # 5. clic en el resultado unico
    time.sleep(pause)
    pyautogui.click(x, y)              # 6. clic en el lienzo
    time.sleep(pause)


def print_plan(resolved, placements, warnings, dry_run):
    print("=" * 72)
    print("  pt-autobuild :: PLAN DE COLOCACION")
    print("=" * 72)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    _ok, _msg = dpi_aware.verify()
    print(f"  {'' if _ok else '[!] '}{_msg}")
    print("-" * 72)
    total = 0
    for cat in CAT_ORDER:
        for r in [g for g in resolved if g["category"] == cat]:
            _, label = CAT_INFO[cat]
            print(f"  {label:<11} x {r['count']:<3}  modelo {r['model']}")
            total += r["count"]
    print(f"  Total: {total} dispositivos")
    print("-" * 72)
    for idx, p in enumerate(placements, 1):
        _, label = CAT_INFO[p["category"]]
        print(f"  {idx:>3}. {label:<11} {p['model']:<12} -> ({p['x']:>5}, {p['y']:>5})")
    if warnings:
        print("-" * 72)
        for w in warnings:
            print(f"  [!] {w}")
    if dry_run:
        print("-" * 72)
        print("  DRY-RUN: no se movera el mouse.")
    print("=" * 72)


def print_catalog(catalog):
    print("  device_catalog.json")
    print("-" * 50)
    for cat in CAT_ORDER:
        cat_key, _ = CAT_INFO[cat]
        default = catalog["defaults"].get(cat_key, "(sin default)")
        print(f"  {cat_key.replace('_', ' ')}  (default: {default})")
        for m in catalog[cat_key]:
            print(f"    - {m}")


def _pt_base_name(placement):
    """Nombre base de Packet Tracer para un placement (Router, Switch, PC, ...)."""
    if placement["category"] == "end_device":
        return PT_BASE_NAME.get(placement["model"], placement["model"])
    return PT_BASE_NAME[placement["category"]]


def _record_tipo(placement):
    """'router' / 'switch' para infra; el modelo en minusculas para end devices."""
    if placement["category"] == "end_device":
        return placement["model"].lower()
    return placement["category"]


def build_topology_record(comando_original, placements, coords, when):
    """
    Arma el dict que se serializa a JSON. Numera los dispositivos siguiendo la
    convencion por defecto de Packet Tracer: contador por nombre base, desde 0.
    'placements' ya viene en el orden en que se colocaron.
    """
    counters = {}
    dispositivos = []
    for idx, p in enumerate(placements, 1):
        base = _pt_base_name(p)
        n = counters.get(base, 0)
        counters[base] = n + 1
        dispositivos.append({
            "id": idx,
            "tipo": _record_tipo(p),
            "modelo": p["model"],
            "nombre": f"{base}{n}",
            "posicion": [p["x"], p["y"]],
        })
    return {
        "fecha": when.isoformat(timespec="seconds"),
        "comando_original": " ".join(comando_original.split()),
        "canvas": coords.get("canvas"),
        "coords_json": coords,
        "dispositivos": dispositivos,
    }


def save_topology_record(record, when):
    """
    Escribe dos archivos junto a build.py:
      - topologia_<fecha>_<hora>.json  (historico, no se sobrescribe)
      - topologia_actual.json          (siempre la ultima ejecucion)
    """
    stamp = when.strftime("%Y-%m-%d_%H-%M")
    stamped = os.path.join(HERE, f"topologia_{stamp}.json")
    actual = os.path.join(HERE, "topologia_actual.json")
    for path in (stamped, actual):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"  Registro guardado: {os.path.basename(stamped)}  (+ topologia_actual.json)")


def main():
    ap = argparse.ArgumentParser(description="Coloca dispositivos en Packet Tracer.")
    ap.add_argument("topology", nargs="?", default=None,
                    help='Ej: "3 routers modelo 4331, 2 switches, 5 PC"')
    ap.add_argument("--file", help="Lee la topologia desde un archivo de texto.")
    ap.add_argument("--catalog", default=CATALOG_PATH,
                    help="Catalogo alternativo (def. device_catalog.json).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Calcula e imprime el plan sin hacer clics.")
    ap.add_argument("--list-models", action="store_true",
                    help="Imprime el catalogo y sale.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre clics en segundos (def. 0.4).")
    ap.add_argument("--filter-delay", type=float, default=0.4,
                    help="Espera tras escribir, antes de clicar el resultado (def. 0.4).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    catalog = load_catalog(args.catalog)

    if args.list_models:
        print_catalog(catalog)
        return

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.topology:
        text = args.topology
    else:
        ap.error("Indica una topologia como argumento o usa --file.")

    groups, warnings = parse_topology(text)
    for w in warnings:
        print(f"  Aviso: {w}")
    if not groups:
        print("No se reconocio ningun dispositivo en la topologia.")
        sys.exit(1)

    # Resolver modelos contra el catalogo
    errors = []
    resolved = []
    for g in groups:
        model = resolve_model(g["category"], g["model"], catalog, errors)
        if model is None:
            continue
        resolved.append({"category": g["category"], "model": model, "count": g["count"]})
    if errors:
        print()
        print("ERROR: la topologia no se puede resolver:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    coords = load_coords()
    placements, layout_warnings = compute_layout(resolved, coords)

    print_plan(resolved, placements, layout_warnings, args.dry_run)

    if args.dry_run:
        return

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0

    countdown(max(0, args.countdown))

    attempted = {"router": 0, "switch": 0, "end_device": 0}
    placed_ok = 0
    aborted = False
    try:
        for p in placements:
            place_device(coords, p["model"], p["x"], p["y"],
                         args.pause, args.filter_delay)
            attempted[p["category"]] += 1
            placed_ok += 1
    except pyautogui.FailSafeException:
        aborted = True
        print("\n  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except KeyboardInterrupt:
        aborted = True
        print("\n  Interrumpido por el usuario.")

    # mouse a un sitio neutro
    try:
        w, h = pyautogui.size()
        pyautogui.moveTo(w // 2, h // 2)
    except Exception:  # noqa: BLE001
        pass

    print()
    print("=" * 72)
    print("  RESUMEN")
    print("=" * 72)
    for cat in CAT_ORDER:
        want = sum(r["count"] for r in resolved if r["category"] == cat)
        if want:
            _, label = CAT_INFO[cat]
            print(f"  {label:<11}: {attempted[cat]} / {want} colocados")
    print("-" * 72)
    print(f"  Total intentado: {placed_ok} / {len(placements)}")
    if aborted:
        print("  Ejecucion incompleta (abortada).")
    print("  Recuerda: los cables se conectan manualmente.")
    print("=" * 72)

    # Registro de la topologia resultante (solo si de verdad se coloco algo).
    # Se guardan unicamente los dispositivos efectivamente colocados.
    if placed_ok > 0:
        now = datetime.datetime.now()
        record = build_topology_record(text, placements[:placed_ok], coords, now)
        try:
            save_topology_record(record, now)
        except OSError as e:  # noqa: BLE001
            print(f"  [!] No se pudo guardar el registro de topologia: {e}")


if __name__ == "__main__":
    main()
