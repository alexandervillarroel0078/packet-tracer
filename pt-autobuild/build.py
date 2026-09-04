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

Sintaxis por REDES agrupadas (compatible con pt-asistente; --file recomendado):
    SWITCHES: Sw1, Sw2
    ROUTERS: R01, R02
    RED Red1: 192.168.10.0/24
    PC1 .2          # host .2 de esa red
    PC2             # IP autoasignada (se reserva .1 como gateway)
    RED Red2: 192.168.20.0/24
    PC3
    - Cada nombre (router/switch/PC) debe ser UNICO en toda la topologia; si se
      repite, se rechaza indicando la linea y el nombre antes de colocar nada.
    - Layout por columnas: una por RED (switch arriba, PCs debajo); routers
      compartidos en la fila superior.
    - Tras colocar los dispositivos se coloca una NOTA con el CIDR de cada red
      (reutiliza add_note.place_note).
    - Por ultimo, configura la IP/mascara/gateway de cada PC (reutiliza
      configure_ip.apply_ip): IP calculada por el parser, mascara de la red,
      gateway = .1 de la red. Si una PC falla, sigue con las demas.
    - El registro (topologia_actual.json) incluye 'notas', 'redes' y, en cada
      PC, 'ip' / 'mascara' / 'gateway'.

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
import ipaddress
import json
import math
import os
import re
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui (fija DPI awareness)
from core import coords as coords_io  # noqa: E402
from core.paths import (CATALOG_PATH, COORDS_PATH, IP_CONFIG_COORDS_PATH,
                        TOPOLOGY_ACTUAL_PATH, TOPOLOGY_HISTORY_DIR)

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala las dependencias con:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

import add_note      # noqa: E402  reutiliza place_note (no duplicar la logica de notas)
import configure_ip  # noqa: E402  reutiliza apply_ip (flujo IP Configuration)

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
        print(f"ERROR: faltan coordenadas en {COORDS_PATH}:")
        for mkey in missing:
            print(f"  - {mkey}")
        print("Ejecuta:  python calibrate.py")
        print("(para un punto suelto:  python calibrate.py --manual <nombre>)")
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
    os.makedirs(TOPOLOGY_HISTORY_DIR, exist_ok=True)
    stamped = os.path.join(TOPOLOGY_HISTORY_DIR, f"topologia_{stamp}.json")
    for path in (stamped, TOPOLOGY_ACTUAL_PATH):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print(f"  Registro guardado: data/topology/history/{os.path.basename(stamped)}")
    print("                     data/topology/topologia_actual.json")


# ======================================================================
#  SINTAXIS POR REDES AGRUPADAS  (compatible con la gramatica de pt-asistente)
#
#      SWITCHES: Sw1, Sw2
#      ROUTERS: R01, R02
#
#      RED Red1: 192.168.10.0/24
#      PC1 .2
#      PC2 .3
#
#      RED Red2: 192.168.20.0/24
#      PC4
#      PC5
#
#  - Cada nombre (router/switch/PC) debe ser UNICO en toda la topologia.
#  - Layout por columnas: una columna por RED (switch arriba, PCs debajo),
#    routers compartidos en la fila superior.
#  - Tras colocar los dispositivos se coloca una NOTA con el CIDR de cada red
#    (reutiliza add_note.place_note; no se duplica esa logica).
# ======================================================================

GROUPED_KEYWORD_RE = re.compile(
    r"^\s*(switch(?:es)?\s*:|routers?\s*:|red\s+[A-Za-z0-9_-]+\s*:)", re.I)
NOTE_BAND = 30          # banda superior reservada para las notas de CIDR
COL_GAP_MIN = 45        # separacion minima recomendada entre columnas de red


def is_grouped_syntax(text):
    """True si alguna linea empieza por SWITCHES: / ROUTERS: / RED ..."""
    return any(GROUPED_KEYWORD_RE.match(ln) for ln in text.splitlines())


def _end_device_model(name):
    """Modelo de end device segun el prefijo alfabetico del nombre (PC1 -> PC)."""
    m = re.match(r"[A-Za-z]+", name or "")
    word = m.group(0).lower() if m else "pc"
    _, implied = WORD_MAP.get(word, ("end_device", "PC"))
    return implied or "PC"


class TopologyError(ValueError):
    """Error de sintaxis/validacion de la topologia por redes (con contexto)."""


def parse_grouped(text):
    """
    Devuelve dict:
        {"routers": [name...], "switches": [name...],
         "redes": [{"nombre", "cidr", "network", "linea",
                    "pcs": [{"nombre", "modelo", "ip"}...]}]}

    Lanza TopologyError (con numero de linea) ante nombre duplicado global,
    CIDR/IP invalidos, host fuera de rango o IP repetida en una red, o
    lineas de PC fuera de un bloque RED. Valida TODO antes de devolver.
    """
    routers, switches, redes = [], [], []
    declared = {}          # nombre de dispositivo -> linea donde se declaro
    red_names = {}          # nombre de red -> linea
    current = None          # bloque RED en curso

    def claim(name, lineno):
        prev = declared.get(name.lower())
        if prev is not None:
            raise TopologyError(
                f"linea {lineno}: nombre '{name}' duplicado "
                f"(ya declarado en la linea {prev}).")
        declared[name.lower()] = lineno

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        m_sw = re.match(r"(?i)switch(?:es)?\s*:\s*(.*)$", line)
        m_rt = re.match(r"(?i)routers?\s*:\s*(.*)$", line)
        m_red = re.match(r"(?i)red\s+([A-Za-z0-9_-]+)\s*:\s*(\S+)\s*$", line)

        if m_sw or m_rt:
            current = None
            names = [n.strip() for n in (m_sw or m_rt).group(1).split(",") if n.strip()]
            if not names:
                raise TopologyError(f"linea {lineno}: '{line}' no lista ningun nombre.")
            for n in names:
                claim(n, lineno)
                (switches if m_sw else routers).append(n)
            continue

        if m_red:
            name, cidr = m_red.group(1), m_red.group(2)
            if name.lower() in red_names:
                raise TopologyError(
                    f"linea {lineno}: red '{name}' duplicada "
                    f"(ya definida en la linea {red_names[name.lower()]}).")
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError as e:
                raise TopologyError(f"linea {lineno}: CIDR invalido '{cidr}': {e}")
            red_names[name.lower()] = lineno
            current = {"nombre": name, "cidr": str(net), "network": net,
                       "linea": lineno, "pcs": []}
            redes.append(current)
            continue

        # linea suelta -> debe ser un PC dentro de un bloque RED
        if current is None:
            raise TopologyError(
                f"linea {lineno}: '{line}' no esta dentro de un bloque 'RED ...:' "
                f"y no es 'SWITCHES:' / 'ROUTERS:'.")

        tokens = line.split()
        if len(tokens) > 2:
            raise TopologyError(
                f"linea {lineno}: '{line}' no se entiende "
                f"(usa 'Nombre' o 'Nombre .N' o 'Nombre A.B.C.D').")
        pname = tokens[0]
        claim(pname, lineno)
        net = current["network"]

        ip = None
        if len(tokens) == 2:
            spec = tokens[1]
            try:
                if spec.startswith("."):
                    host_n = int(spec[1:])
                    addr = net.network_address + host_n
                else:
                    addr = ipaddress.ip_address(spec)
            except ValueError as e:
                raise TopologyError(f"linea {lineno}: IP/host invalido '{spec}': {e}")
            if addr not in net:
                raise TopologyError(
                    f"linea {lineno}: {addr} esta fuera de {current['cidr']}.")
            if net.prefixlen < 31 and addr in (net.network_address,
                                               net.broadcast_address):
                raise TopologyError(
                    f"linea {lineno}: {addr} es la direccion de red o de broadcast "
                    f"de {current['cidr']}, no vale para un PC.")
            ip = str(addr)
            if any(pc["ip"] == ip for pc in current["pcs"]):
                raise TopologyError(
                    f"linea {lineno}: la IP {ip} ya se uso en la red {current['nombre']}.")

        current["pcs"].append({"nombre": pname,
                               "modelo": _end_device_model(pname),
                               "ip": ip})

    if not (routers or switches or redes):
        raise TopologyError("no se reconocio ninguna clausula "
                            "(SWITCHES: / ROUTERS: / RED ...).")

    # autoasignacion de IPs faltantes (se reserva .1 como gateway)
    for red in redes:
        net = red["network"]
        used = {pc["ip"] for pc in red["pcs"] if pc["ip"]}
        gw = str(net.network_address + 1)
        free = (str(h) for h in net.hosts() if str(h) not in used and str(h) != gw)
        for pc in red["pcs"]:
            if pc["ip"] is None:
                pc["ip"] = next(free, None)
                if pc["ip"] is None:
                    raise TopologyError(
                        f"la red {red['nombre']} ({red['cidr']}) no tiene "
                        f"direcciones libres para todos sus PCs.")
    return {"routers": routers, "switches": switches, "redes": redes}


def compute_grouped_layout(parsed, coords, catalog):
    """
    Devuelve (placements, notes, warnings).
        placements: [{category, model, nombre, x, y, ip?}]  en orden de colocacion
        notes:      [{texto, red, x, y}]
    Una columna por red (switch arriba, PCs en cuadricula debajo); routers y
    switches sobrantes en filas superiores compartidas; notas en una banda
    reservada encima de todo.
    """
    x0, y0 = coords["canvas"]["top_left"]
    x1, y1 = coords["canvas"]["bottom_right"]
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)

    errors = []
    router_model = resolve_model("router", None, catalog, errors) if parsed["routers"] else None
    switch_model = resolve_model("switch", None, catalog, errors) if parsed["switches"] else None
    if errors:
        raise TopologyError("; ".join(errors))

    routers = parsed["routers"]
    switches = parsed["switches"]
    redes = parsed["redes"]
    n_net = len(redes)

    usable_h = y1 - y0
    row_gap = max(ROW_GAP_MIN, usable_h * ROW_GAP_FRAC)

    warnings = []
    placements = []
    notes = []

    cursor_y = y0
    notes_y = round(cursor_y + 6)
    cursor_y += NOTE_BAND

    router_y = None
    if routers:
        router_y = round(cursor_y)
        cursor_y += row_gap

    extra_switches = switches[n_net:]
    extra_switch_y = None
    if extra_switches:
        warnings.append(f"{len(extra_switches)} switch(es) sin red asignada: van en "
                        f"una fila compartida arriba.")
        extra_switch_y = round(cursor_y)
        cursor_y += row_gap

    switch_y = round(cursor_y)
    cursor_y += row_gap
    pc_y_start = round(cursor_y)

    # Routers compartidos
    for x, name in zip(spread(len(routers), x0, x1), routers):
        placements.append({"category": "router", "model": router_model,
                           "nombre": name, "x": clamp(round(x), x0, x1), "y": router_y})

    # Switches sobrantes
    for x, name in zip(spread(len(extra_switches), x0, x1), extra_switches):
        placements.append({"category": "switch", "model": switch_model,
                           "nombre": name, "x": clamp(round(x), x0, x1),
                           "y": extra_switch_y})

    if n_net and len(switches) < n_net:
        warnings.append(f"hay {n_net} redes pero solo {len(switches)} switch(es): "
                        f"esas columnas quedan sin switch.")

    col_centers = spread(n_net, x0, x1)
    col_w = (x1 - x0) / n_net if n_net else (x1 - x0)
    if n_net > 1 and col_w < COL_GAP_MIN + END_DX:
        warnings.append(f"{n_net} columnas en {x1 - x0}px (~{round(col_w)}px cada una): "
                        f"las redes pueden tocarse.")

    for i, red in enumerate(redes):
        cx = col_centers[i]
        red["switch_name"] = switches[i] if i < len(switches) else None

        if red["switch_name"]:
            placements.append({"category": "switch", "model": switch_model,
                               "nombre": red["switch_name"],
                               "x": clamp(round(cx), x0, x1), "y": switch_y})

        net = red["network"]
        mascara = str(net.netmask)
        gateway = str(net.network_address + 1)   # .1 reservado como gateway

        pcs = red["pcs"]
        per_row = max(1, int(col_w // END_DX))
        per_row = min(per_row, len(pcs)) or 1
        for k, pc in enumerate(pcs):
            ccol = k % per_row
            crow = k // per_row
            px = cx + (ccol - (per_row - 1) / 2) * END_DX
            py = pc_y_start + crow * END_DY
            placements.append({"category": "end_device", "model": pc["modelo"],
                               "nombre": pc["nombre"], "ip": pc["ip"],
                               "mascara": mascara, "gateway": gateway,
                               "x": clamp(round(px), x0, x1),
                               "y": clamp(round(py), y0, y1)})

        notes.append({"texto": red["cidr"], "red": red["nombre"],
                      "x": clamp(round(cx), x0, x1), "y": notes_y})

    return placements, notes, warnings


def build_grouped_record(text, placements, notes, redes, coords, when):
    dispositivos = []
    for idx, p in enumerate(placements, 1):
        d = {"id": idx, "tipo": _record_tipo(p), "modelo": p["model"],
             "nombre": p["nombre"], "posicion": [p["x"], p["y"]]}
        if p.get("ip"):
            d["ip"] = p["ip"]
        if p.get("mascara"):
            d["mascara"] = p["mascara"]
        if p.get("gateway"):
            d["gateway"] = p["gateway"]
        dispositivos.append(d)
    return {
        "fecha": when.isoformat(timespec="seconds"),
        "comando_original": " ".join(text.split()),
        "canvas": coords.get("canvas"),
        "coords_json": coords,
        "dispositivos": dispositivos,
        "notas": [{"texto": n["texto"], "red": n["red"],
                   "posicion": [n["x"], n["y"]]} for n in notes],
        "redes": [{"nombre": r["nombre"], "cidr": r["cidr"]} for r in redes],
    }


def print_grouped_plan(parsed, placements, notes, pcs_to_cfg, ip_missing,
                       warnings, dry_run):
    print("=" * 72)
    print("  pt-autobuild :: PLAN DE COLOCACION (sintaxis por redes)")
    print("=" * 72)
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    _ok, _msg = dpi_aware.verify()
    print(f"  {'' if _ok else '[!] '}{_msg}")
    print("-" * 72)
    by_name = {p["nombre"]: p for p in placements}
    if parsed["routers"]:
        print(f"  Routers : {', '.join(parsed['routers'])}")
    for red in parsed["redes"]:
        sw = red.get("switch_name") or "(sin switch)"
        print(f"  {red['nombre']}  {red['cidr']}   switch {sw}")
        for pc in red["pcs"]:
            p = by_name.get(pc["nombre"], {})
            print(f"     {pc['nombre']:<10} {(pc['ip'] or '(sin ip)'):<15} "
                  f"-> ({p.get('x', '?')}, {p.get('y', '?')})")
    print("-" * 72)
    print("  1) Orden de colocacion:")
    for idx, p in enumerate(placements, 1):
        print(f"  {idx:>3}. {p['category']:<11} {p['model']:<12} {p['nombre']:<10} "
              f"-> ({p['x']:>5}, {p['y']:>5})")
    print("-" * 72)
    print("  2) Notas (CIDR por red)  [clic de foco -> 'n' -> clic -> texto -> Escape]:")
    for n in notes:
        print(f'     "{n["texto"]}"  -> ({n["x"]:>5}, {n["y"]:>5})   [{n["red"]}]')
    print("-" * 72)
    print("  3) Configuracion IP de las PCs  (DESPUES de colocar todo y las notas):")
    if ip_missing:
        print(f"     [!] SE OMITE: faltan puntos en data/ip_config_coords.json: "
              f"{', '.join(ip_missing)}")
        print("         Calibra con:  python configure_ip.py --calibrate")
    elif not pcs_to_cfg:
        print("     (no hay PCs con IP asignada)")
    else:
        for p in pcs_to_cfg:
            print(f"     {p['nombre']:<10} IP {p['ip']:<15} mask {p['mascara']:<15} "
                  f"gw {p['gateway']}   (doble clic en {p['x']},{p['y']})")
    if warnings:
        print("-" * 72)
        for w in warnings:
            print(f"  [!] {w}")
    if dry_run:
        print("-" * 72)
        print("  DRY-RUN: no se movera el mouse ni se escribira el registro.")
    print("=" * 72)


def run_grouped(text, catalog, args):
    """Camino de la sintaxis por redes. No toca el camino de la sintaxis simple."""
    try:
        parsed = parse_grouped(text)
    except TopologyError as e:
        print()
        print("ERROR: la topologia no es valida (no se coloco nada):")
        print(f"  - {e}")
        sys.exit(1)

    coords = load_coords()
    try:
        placements, notes, warnings = compute_grouped_layout(parsed, coords, catalog)
    except TopologyError as e:
        print()
        print("ERROR: no se pudo resolver el layout:")
        print(f"  - {e}")
        sys.exit(1)

    # Paso 3 (config IP): se hace tras colocar todo. Aqui solo se comprueba
    # que ip_config_coords.json esta calibrado; si no, se omite con aviso.
    pcs_to_cfg = [p for p in placements
                  if p["category"] == "end_device" and p.get("ip")]
    ip_data = coords_io.load_coords(IP_CONFIG_COORDS_PATH)
    ip_missing = [k for k in configure_ip.REQUIRED_COORDS if ip_data.get(k) is None]

    print_grouped_plan(parsed, placements, notes, pcs_to_cfg, ip_missing,
                       warnings, args.dry_run)
    if args.dry_run:
        return

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    countdown(max(0, args.countdown))

    placed_ok = 0
    notes_ok = 0
    ip_ok = 0
    ip_fail = 0
    aborted = False
    try:
        for p in placements:
            place_device(coords, p["model"], p["x"], p["y"],
                         args.pause, args.filter_delay)
            placed_ok += 1
        for n in notes:
            # focus_xy recupera el foco de la ventana entre nota y nota
            # (tras el Escape anterior el foco sale de Packet Tracer).
            add_note.place_note(n["texto"], n["x"], n["y"],
                                pause=args.pause, focus_xy=(n["x"], n["y"]))
            notes_ok += 1
    except pyautogui.FailSafeException:
        aborted = True
        print("\n  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except KeyboardInterrupt:
        aborted = True
        print("\n  Interrumpido por el usuario.")

    # --- Paso 3: configurar IP/mascara/gateway de cada PC ---------------
    if not aborted and pcs_to_cfg:
        print()
        if ip_missing:
            print(f"  [!] No se configuran IPs: faltan puntos calibrados "
                  f"({', '.join(ip_missing)}).")
            print("      Calibra con:  python configure_ip.py --calibrate")
        else:
            print(f"  Configurando IP de {len(pcs_to_cfg)} PC(s)...")
            for p in pcs_to_cfg:
                try:
                    configure_ip.apply_ip(ip_data, p["x"], p["y"], p["ip"],
                                          p["mascara"], p["gateway"],
                                          pause=args.pause)
                    ip_ok += 1
                    print(f"    OK    {p['nombre']:<10} {p['ip']}/{p['mascara']} "
                          f"gw {p['gateway']}")
                except pyautogui.FailSafeException:
                    aborted = True
                    print("\n  ABORTADO por failsafe durante la configuracion IP.")
                    break
                except KeyboardInterrupt:
                    aborted = True
                    print("\n  Interrumpido durante la configuracion IP.")
                    break
                except Exception as e:  # noqa: BLE001  (una PC falla -> seguir con las demas)
                    ip_fail += 1
                    print(f"    FALLO {p['nombre']:<10} ({type(e).__name__}: {e})")

    try:
        w, h = pyautogui.size()
        pyautogui.moveTo(w // 2, h // 2)
    except Exception:  # noqa: BLE001
        pass

    print()
    print("=" * 72)
    print("  RESUMEN")
    print("=" * 72)
    print(f"  Dispositivos: {placed_ok} / {len(placements)}")
    print(f"  Notas CIDR  : {notes_ok} / {len(notes)}")
    if pcs_to_cfg:
        if ip_missing:
            print(f"  Config IP   : omitida (falta calibracion) / {len(pcs_to_cfg)} PCs")
        else:
            print(f"  Config IP   : {ip_ok} OK / {ip_fail} fallaron / "
                  f"{len(pcs_to_cfg)} PCs")
    if aborted:
        print("  Ejecucion incompleta (abortada).")
    print("  Recuerda: los cables se conectan manualmente.")
    print("=" * 72)

    if placed_ok > 0:
        now = datetime.datetime.now()
        record = build_grouped_record(
            text, placements[:placed_ok], notes[:notes_ok], parsed["redes"], coords, now)
        try:
            save_topology_record(record, now)
        except OSError as e:  # noqa: BLE001
            print(f"  [!] No se pudo guardar el registro de topologia: {e}")


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

    # Sintaxis por redes agrupadas (SWITCHES: / ROUTERS: / RED ...).
    # La sintaxis simple ("2 routers, 2 switches, 4 PC") sigue igual, debajo.
    if is_grouped_syntax(text):
        run_grouped(text, catalog, args)
        return

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
