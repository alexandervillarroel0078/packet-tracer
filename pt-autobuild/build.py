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
    RED Red1: 192.168.10.0/24 R01          # R01 es el gateway (interfaz LAN)
    PC1 .2          # host .2 de esa red
    PC2             # IP autoasignada (se reserva .1 como gateway)
    RED Red2: 192.168.20.0/24 R02 Gig0/1/0 # interfaz LAN explicita
    PC3
    ENLACES:
    R01 Se0/1/0 R02 10.0.0.0/30    # ROUTER1 IFAZ ROUTER2 CIDR (misma interfaz en ambos)

    Formas adicionales (todo lo de arriba sigue funcionando igual):
    - ROUTERS:/SWITCHES: agrupados por modelo (cada dispositivo puede pedir
      un modelo distinto; sin bloque, sigue usando el default del catalogo):
          ROUTERS:
          4331: R01, R02
          4321: R03, R04
    - 'RED ' es opcional en el encabezado ('Red1: cidr' == 'RED Red1: cidr').
    - Conector explicito, como PRIMERA linea del bloque RED (router y
      destino ya declarados ANTES en el texto -- a diferencia del token
      inline, este SI exige ese orden):
          R01-Sw1     # switch: PCs de esta red van a Sw1, colgado de R01
          R03-PC5     # directo: PC5 (unica PC de esta red) va al LAN de R03
      No se puede combinar con el token inline ('RED ...: cidr ROUTER') en
      la misma red -- error explicito si se repiten.
    - Cada nombre (router/switch/PC) debe ser UNICO en toda la topologia; si se
      repite, se rechaza indicando la linea y el nombre antes de colocar nada.
    - Layout por columnas: una por RED (switch arriba, PCs debajo); routers
      compartidos en la fila superior.
    - Tras colocar cada dispositivo se renombra su LABEL VISUAL (el nombre
      debajo del icono) para que coincida con el nombre declarado (ej.
      "Router11" -> "R01"); reutiliza rename_label.rename_label. Es SOLO el
      label del lienzo, no el hostname por CLI (eso es routers/
      configure_router.py, aparte). Offset confirmado a mano: 38px para
      router; switch/end_device arrancan con el mismo valor, pendiente de
      confirmar (ver rename_label.LABEL_OFFSET_Y).
    - Tras renombrar, se coloca una NOTA con el CIDR de cada red
      (reutiliza add_note.place_note).
    - 'RED ...: CIDR [ROUTER [IFAZ]]': si se indica ROUTER, se calcula (SOLO
      en memoria, no se configura nada en Packet Tracer) la IP de su interfaz
      LAN (.1 de la red; IFAZ por defecto 'Gig0/0/0') y se coloca una nota
      chica junto al router, ej. "Gig0/0/0 .1/24". Sin ROUTER, se omite esa
      nota (compatible con topologias viejas).
    - 'ENLACES:' (opcional, va despues de las RED): una linea por enlace
      punto a punto entre dos routers ya declarados:
          ROUTER1 IFAZ ROUTER2 CIDR/30
      La IFAZ se reutiliza igual en ambos routers (no se especifica dos
      veces). Se calcula (solo en memoria) .1 para ROUTER1 y .2 para
      ROUTER2, y se coloca una nota junto a cada extremo, ej. "Se0/1/0
      .1/30" en ROUTER1 y "Se0/1/0 .2/30" en ROUTER2. No se configura
      ninguna IP real. Ademas se
      coloca una nota con el CIDR completo del enlace en el punto medio
      entre ambos routers, ej. "10.0.0.0/30". Si 2+ enlaces comparten el
      mismo par de routers (enlaces duplicados), sus 3 notas (2 de interfaz
      + la del punto medio) reciben un offset perpendicular escalonado
      (LINK_STAGGER_STEP px) para no superponerse, quedando en 'carriles'
      paralelos a la linea entre los dos routers.
    - Por ultimo, configura la IP/mascara/gateway de cada PC (reutiliza
      configure_ip.apply_ip): IP calculada por el parser, mascara de la red,
      gateway = .1 de la red. Si una PC falla, sigue con las demas.
    - El registro (topologia_actual.json) incluye 'notas', 'redes' y, en cada
      PC, 'ip' / 'mascara' / 'gateway'. Cada router con interfaces declaradas
      (LAN y/o de enlace) incluye 'interfaces': [{nombre, ip, mascara,
      posicion}]. Tambien incluye 'enlaces': [{r1, if1, r2, if2, cidr, ip1,
      ip2, mascara, nota_red: {texto, posicion}}] por cada 'ENLACES:' --
      todo esto es solo registro/memoria, no se aplica en Packet Tracer.

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
import rename_label  # noqa: E402  reutiliza rename_label (no duplicar la logica de rename)

# --- Parametros de layout (pixeles) --------------------------------------
MIN_DX = 55          # separacion horizontal minima recomendada entre dispositivos
ROW_GAP_MIN = 80     # separacion vertical minima entre filas
ROW_GAP_FRAC = 0.18  # o esta fraccion del alto util, lo que sea mayor
END_DX = 55          # separacion horizontal entre end devices de un grupo
END_DY = 55          # separacion vertical entre end devices de un grupo

# --- Notas de interfaz (LAN de router + enlaces punto a punto) -----------
# Solo afectan el TEXTO/POSICION de la nota; no se configura ninguna IP real.
DEFAULT_LAN_IFACE = "Gig0/0/0"   # interfaz LAN por defecto si 'RED ...' no la indica
INTERFACE_NOTE_OFFSET = 25       # px de separacion entre el router y su nota de interfaz
LINK_STAGGER_STEP = 20           # px entre enlaces duplicados (mismo par de routers)

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
    cat.setdefault("router_interfaces", {})
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


def calculate_interface_position(router_pos, neighbor_pos, offset=INTERFACE_NOTE_OFFSET):
    """
    Punto a 'offset' px de router_pos, en direccion al vecino (neighbor_pos).

    Se usa solo para separar visualmente la NOTA de una interfaz del icono
    del router -- no es una posicion real de Packet Tracer ni mueve nada.
    'neighbor_pos' es la posicion del otro extremo: el switch de la red para
    una interfaz LAN, o el otro router para un enlace punto a punto.

    Si router_pos == neighbor_pos (distancia 0, no deberia pasar en la
    practica) usa (0, -1) -- arriba del router -- para no dividir por cero.
    """
    rx, ry = router_pos
    nx, ny = neighbor_pos
    dx, dy = nx - rx, ny - ry
    dist = math.hypot(dx, dy)
    ux, uy = (dx / dist, dy / dist) if dist else (0.0, -1.0)
    return (round(rx + ux * offset), round(ry + uy * offset))


def _perp_unit(dx, dy):
    """Vector unitario perpendicular a (dx, dy) (rotado 90 grados).

    Se usa para escalonar notas que colisionarian: cuando 2+ enlaces
    conectan el mismo par de routers, sus notas (interfaz + punto medio)
    caerian todas en el mismo punto; se las separa corriendolas de a
    LINK_STAGGER_STEP px en esta direccion perpendicular a la linea entre
    los dos routers, para que queden en 'carriles' paralelos.

    Si (dx, dy) es el vector nulo (no deberia pasar en la practica), usa
    (1, 0) de forma arbitraria para no dividir por cero.
    """
    dist = math.hypot(dx, dy)
    return (-dy / dist, dx / dist) if dist else (1.0, 0.0)


# --- Cableado de ENLACES (solo router-router; switch/PC quedan para otra
# etapa) -----------------------------------------------------------------
def compute_menu_index(model, iface_name, used_ifaces, catalog, category="router",
                       tipo=None):
    """
    Indice (0-based) que ocuparia 'iface_name' en el menu de conexiones de
    Packet Tracer para un dispositivo de este modelo, DADO el estado de ESE
    dispositivo puntual.

    Confirmado a mano: Packet Tracer SACA del menu las interfaces que ya
    tienen un cable puesto (no las muestra deshabilitadas) -- por eso el
    indice depende de CUANTAS y CUALES interfaces de este dispositivo ya se
    cablearon hasta este punto del run ('used_ifaces'), no solo del modelo.

    Tambien CONFIRMADO A MANO (routers): la lista se FILTRA segun el TIPO
    DE CABLE seleccionado -- siempre aparece el mismo prefijo de consolas
    (USB Console, Auxiliary, Console), pero despues solo se listan las
    interfaces de datos COMPATIBLES con ese cable (ej. solo las Serial si
    elegiste un cable serial, solo las Gigabit si elegiste copper). Por
    eso 'catalog["router_interfaces"][model]' es un dict {tipo: [...]}, no
    una lista plana, y hace falta pasar 'tipo' para los modelos asi.
    'catalog["switch_interfaces"][model]' sigue siendo una lista plana
    (solo se probo con copper hasta ahora); si algun modelo de switch
    tambien varia por tipo, se lo puede migrar al mismo formato de dict y
    esta funcion lo soporta igual (detecta el tipo de valor).

    category: 'router' o 'switch' -- decide si se busca en
    catalog['router_interfaces'] o catalog['switch_interfaces']. El
    cableado automatico de ENLACES (compute_cabling_plan) solo usa
    'router' (alcance confirmado: router-router); 'switch' esta pensado
    para uso manual/exploratorio (ej. cable_link.py probado a mano contra
    un switch) hasta que se decida integrar router-switch a build.py.

    Se filtra sacando 'used_ifaces' de la lista completa y se busca la
    posicion de 'iface_name' en la lista restante.
    """
    cat_key = "router_interfaces" if category == "router" else "switch_interfaces"
    entry = catalog.get(cat_key, {}).get(model)
    if entry is None:
        raise TopologyError(
            f"el catalogo no tiene '{cat_key}' para el modelo '{model}' "
            f"(hace falta para calcular la posicion en el menu de conexiones).")
    if isinstance(entry, dict):
        if tipo is None:
            raise TopologyError(
                f"'{cat_key}[{model}]' depende del tipo de cable (confirmado a "
                f"mano); falta indicar 'tipo' (ej. 'serial', 'copper').")
        full_order = entry.get(tipo)
        if not full_order:
            raise TopologyError(
                f"'{cat_key}[{model}]' no tiene datos para el tipo de cable "
                f"'{tipo}'. Tipos disponibles: {', '.join(entry.keys())}.")
    else:
        full_order = entry
    remaining = [i for i in full_order if i not in used_ifaces]
    try:
        return remaining.index(iface_name)
    except ValueError:
        raise TopologyError(
            f"la interfaz '{iface_name}' no esta en la lista de '{model}' "
            f"({', '.join(full_order)}) o ya esta marcada como usada.")


def compute_cabling_plan(parsed, placements, catalog):
    """
    Devuelve (plan, warnings).
        plan: [{"r1", "if1", "idx1", "r2", "if2", "idx2", "cidr", "linea"}, ...]
              EN EL ORDEN declarado en 'ENLACES:', con el indice de menu YA
              calculado para cada extremo.

    Simula el efecto de "las interfaces cableadas desaparecen del menu"
    acumulando, por router, que interfaces se van "gastando" a medida que
    se procesan los enlaces en orden -- exactamente lo que pasaria en
    Packet Tracer si se cablean en ese mismo orden.

    Asume que los routers arrancan SIN NINGUNA interfaz ocupada (recien
    colocados, nada mas los toco todavia); por eso el cableado va
    INMEDIATAMENTE despues de colocar/renombrar, antes de cualquier nota.

    Si al catalogo le falta 'router_interfaces' para el modelo de algun
    router (dato pendiente de completar a mano mirando Packet Tracer), ESE
    enlace puntual se OMITE del plan con un aviso -- no es fatal, no
    bloquea colocacion/notas/IP del resto de la topologia.
    """
    model_by_router = {p["nombre"]: p["model"] for p in placements
                       if p["category"] == "router"}
    used = {}   # nombre de router -> set de interfaces ya cableadas en este run
    plan = []
    warnings = []
    for enl in parsed.get("enlaces", []):
        r1, if1, r2, if2 = enl["r1"], enl["if1"], enl["r2"], enl["if2"]
        model1, model2 = model_by_router.get(r1), model_by_router.get(r2)
        if model1 is None or model2 is None:
            warnings.append(f"ENLACES linea {enl['linea']}: no se pudo ubicar el "
                            f"modelo de '{r1}' o '{r2}'; se omite el cableado.")
            continue
        u1 = used.setdefault(r1, set())
        u2 = used.setdefault(r2, set())
        try:
            # ENLACES: siempre son cables SERIALES (alcance confirmado:
            # router-router). El menu de un router se filtra por tipo de
            # cable (confirmado a mano), por eso se pasa 'tipo' aca.
            idx1 = compute_menu_index(model1, if1, u1, catalog, tipo="serial")
            idx2 = compute_menu_index(model2, if2, u2, catalog, tipo="serial")
        except TopologyError as e:
            warnings.append(f"ENLACES linea {enl['linea']}: {e} (falta completar "
                            f"'router_interfaces' en el catalogo); se omite el "
                            f"cableado de este enlace.")
            continue
        plan.append({"r1": r1, "if1": if1, "idx1": idx1,
                    "r2": r2, "if2": if2, "idx2": idx2,
                    "cidr": enl["cidr"], "linea": enl["linea"]})
        u1.add(if1)
        u2.add(if2)
    return plan, warnings


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
    r"^\s*(switch(?:es)?\s*:|routers?\s*:|enlaces\s*:|"
    r"(?:red\s+)?[A-Za-z0-9_-]+\s*:\s*\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})", re.I)
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


def _looks_like_cidr(s):
    """True si 's' parsea como red IPv4/IPv6 valida (ipaddress.ip_network).

    Se usa para desambiguar, dentro de un bloque 'ROUTERS:'/'SWITCHES:'
    agrupado por modelo, una linea 'MODELO: nombre, nombre' (no es CIDR) de
    una linea que en realidad es el encabezado de la siguiente RED (SI es
    CIDR) y por lo tanto cierra el bloque.
    """
    try:
        ipaddress.ip_network(s, strict=False)
        return True
    except ValueError:
        return False


def parse_grouped(text):
    """
    Devuelve dict:
        {"routers": [name...], "switches": [name...],
         "router_models": {name: modelo_explicito, ...},
         "switch_models": {name: modelo_explicito, ...},
         "redes": [{"nombre", "cidr", "network", "linea",
                    "router_lan", "iface_lan",
                    "switch_name", "switch_explicit", "direct",
                    "pcs": [{"nombre", "modelo", "ip"}...]}],
         "enlaces": [{"r1", "if1", "r2", "if2", "cidr", "network", "linea",
                      "ip1", "ip2", "mascara", "prefixlen"}]}

    'router_models'/'switch_models' solo traen entrada para los nombres con
    modelo EXPLICITO (bloque agrupado por modelo, ver sintaxis abajo);
    ausente = usar el default del catalogo, igual que siempre.

    'router_lan'/'iface_lan' e 'ip1'/'ip2' de los enlaces son SOLO datos en
    memoria para el texto de las notas de interfaz; no se configura ninguna
    IP real en Packet Tracer (eso es responsabilidad de otro flujo, aparte).
    'switch_name'/'switch_explicit'/'direct' quedan fijados aca si la RED
    declara un conector (ver mas abajo); si no, 'switch_explicit'=False y
    'direct'=False, y compute_grouped_layout() asigna el switch por
    POSICION, exactamente como antes.

    Sintaxis aceptada (todo lo viejo sigue funcionando sin cambios):
        SWITCHES: Sw1, Sw2                    # flat, modelo default (viejo)
        ROUTERS:                              # bloque agrupado por modelo
        4331: R01, R02
        4321: R03, R04
        RED Red1: 192.168.1.0/24 R01 [IFAZ]   # 'RED ' opcional; token de
                                               # router/interfaz inline (viejo)
        R01-Sw1                                # conector, 1ra linea del
                                                # bloque RED: switch explicito
        R03-PC5                                # conector: conexion directa
                                                # (sin switch); PC5 debe ser
                                                # la UNICA PC de esa red
        ENLACES:
        R01 Se0/1/0 R02 10.0.0.0/30            # misma interfaz en ambos routers

    Lanza TopologyError (con numero de linea) ante: nombre duplicado global,
    CIDR/IP invalidos, host fuera de rango o IP repetida en una red, modelo
    no reconocido en un bloque agrupado (via resolve_model, en
    compute_grouped_layout), router o switch de un CONECTOR no declarado
    TODAVIA (deben ir antes en el texto -- a diferencia del token inline y
    de 'ENLACES:', que se validan al final con orden libre), conector +
    token inline juntos en la misma RED, conexion directa con != 1 PC o con
    el nombre equivocado, switch reutilizado en 2 conectores, interfaz
    repetida en un mismo router, o lineas fuera de un bloque RED/ENLACES.
    Valida TODO antes de devolver.
    """
    routers, switches, redes, enlaces = [], [], [], []
    router_models, switch_models = {}, {}
    routers_lower, switches_lower = set(), set()
    declared = {}          # nombre de dispositivo -> linea donde se declaro
    red_names = {}          # nombre de red -> linea
    current = None          # bloque RED en curso
    in_enlaces = False      # bloque ENLACES en curso
    in_router_group = False # bloque "ROUTERS:" agrupado por modelo, en curso
    in_switch_group = False # idem para "SWITCHES:"

    def claim(name, lineno):
        prev = declared.get(name.lower())
        if prev is not None:
            raise TopologyError(
                f"linea {lineno}: nombre '{name}' duplicado "
                f"(ya declarado en la linea {prev}).")
        declared[name.lower()] = lineno

    def add_router(name, model, lineno):
        claim(name, lineno)
        routers.append(name)
        routers_lower.add(name.lower())
        if model:
            router_models[name] = model

    def add_switch(name, model, lineno):
        claim(name, lineno)
        switches.append(name)
        switches_lower.add(name.lower())
        if model:
            switch_models[name] = model

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue

        m_sw = re.match(r"(?i)switch(?:es)?\s*:\s*(.*)$", line)
        m_rt = re.match(r"(?i)routers?\s*:\s*(.*)$", line)

        if m_sw or m_rt:
            current = None
            in_enlaces = False
            rest = (m_sw or m_rt).group(1).strip()
            if rest:
                # FORMA VIEJA: flat, sin modelo por dispositivo (todos usan
                # el default del catalogo, como siempre).
                in_router_group = in_switch_group = False
                names = [n.strip() for n in rest.split(",") if n.strip()]
                if not names:
                    raise TopologyError(f"linea {lineno}: '{line}' no lista ningun nombre.")
                for n in names:
                    if m_sw:
                        add_switch(n, None, lineno)
                    else:
                        add_router(n, None, lineno)
            else:
                # FORMA NUEVA: bloque agrupado por modelo; las lineas
                # siguientes son "MODELO: nombre, nombre, ...".
                in_switch_group = bool(m_sw)
                in_router_group = bool(m_rt)
            continue

        m_enl = re.match(r"(?i)enlaces\s*:\s*$", line)
        if m_enl:
            current = None
            in_router_group = in_switch_group = False
            in_enlaces = True
            continue

        if in_router_group or in_switch_group:
            m_grp = re.match(r"^([^\s:,]+)\s*:\s*(.+)$", line)
            if m_grp:
                model_tok, rest = m_grp.group(1), m_grp.group(2)
                first_val = rest.split()[0] if rest.split() else ""
                if not _looks_like_cidr(first_val):
                    names = [n.strip() for n in rest.split(",") if n.strip()]
                    if not names:
                        raise TopologyError(
                            f"linea {lineno}: '{line}' no lista ningun nombre "
                            f"para el modelo '{model_tok}'.")
                    for n in names:
                        if in_router_group:
                            add_router(n, model_tok, lineno)
                        else:
                            add_switch(n, model_tok, lineno)
                    continue
            # No era una linea de modelo (o el valor SI parece un CIDR): el
            # bloque termina aca; esta linea se reinterpreta mas abajo
            # (normalmente el encabezado de la siguiente RED).
            in_router_group = in_switch_group = False

        m_red = re.match(r"(?i)(?:red\s+)?([A-Za-z0-9_-]+)\s*:\s*(\S+)(?:\s+(.*))?$", line)
        if m_red:
            name, cidr, extra = m_red.group(1), m_red.group(2), m_red.group(3)
            extra_tokens = extra.split() if extra else []
            if len(extra_tokens) > 2:
                raise TopologyError(
                    f"linea {lineno}: '{line}' - despues del CIDR solo se acepta "
                    f"'ROUTER [INTERFAZ]'.")
            router_lan = extra_tokens[0] if extra_tokens else None
            iface_lan = extra_tokens[1] if len(extra_tokens) > 1 else None
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
                       "linea": lineno, "pcs": [],
                       "router_lan": router_lan, "iface_lan": iface_lan,
                       "switch_name": None, "switch_explicit": False,
                       "direct": False, "_connector_checked": False,
                       "_pending_direct_pc": None}
            in_enlaces = False
            redes.append(current)
            continue

        if in_enlaces:
            tokens = line.split()
            if len(tokens) != 4:
                raise TopologyError(
                    f"linea {lineno}: '{line}' no tiene el formato "
                    f"'ROUTER1 IFAZ ROUTER2 CIDR' (ej. "
                    f"'R01 Se0/1/0 R02 10.0.0.0/30'; la interfaz se reutiliza "
                    f"igual en ambos routers del enlace).")
            r1, iface, r2, cidr = tokens
            if r1.lower() == r2.lower():
                raise TopologyError(
                    f"linea {lineno}: el enlace conecta '{r1}' consigo mismo.")
            try:
                net = ipaddress.ip_network(cidr, strict=False)
            except ValueError as e:
                raise TopologyError(f"linea {lineno}: CIDR invalido '{cidr}': {e}")
            if net.num_addresses < 4:
                raise TopologyError(
                    f"linea {lineno}: '{cidr}' es demasiado chico para un enlace "
                    f"punto a punto (usa /30 o mas grande).")
            # 'if1'/'if2' quedan iguales (mismo nombre de interfaz en ambos
            # routers): el resto del pipeline (notas de interfaz, JSON,
            # validacion de interfaz repetida) sigue igual sin cambios, ya
            # que solo consume enl['if1']/enl['if2'] sin asumir que difieren.
            enlaces.append({"r1": r1, "if1": iface, "r2": r2, "if2": iface,
                            "cidr": str(net), "network": net, "linea": lineno})
            continue

        # linea suelta -> conector explicito (solo la 1ra del bloque RED) o PC
        if current is None:
            raise TopologyError(
                f"linea {lineno}: '{line}' no esta dentro de un bloque 'RED ...:' "
                f"ni 'ENLACES:', y no es 'SWITCHES:' / 'ROUTERS:'.")

        if not current["_connector_checked"]:
            current["_connector_checked"] = True
            m_conn = re.match(r"^([^\s-]+)-(.+)$", line)
            if m_conn:
                conn_router, conn_dest = m_conn.group(1), m_conn.group(2)
                if conn_router.lower() in routers_lower:
                    if current["router_lan"]:
                        raise TopologyError(
                            f"linea {lineno}: la RED '{current['nombre']}' ya declara "
                            f"el router '{current['router_lan']}' en el encabezado; "
                            f"no se puede repetir con el conector '{line}'.")
                    current["router_lan"] = conn_router
                    current["iface_lan"] = current["iface_lan"] or DEFAULT_LAN_IFACE
                    if conn_dest.lower() in switches_lower:
                        current["switch_name"] = conn_dest
                        current["switch_explicit"] = True
                    else:
                        current["direct"] = True
                        current["_pending_direct_pc"] = conn_dest
                    continue
                # el token antes del guion no es un router conocido -> no es
                # un conector (ej. una PC cuyo nombre trae un guion por
                # coincidencia); sigue abajo como PC normal.

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

    # --- Validacion de routers/switches/interfaces referenciados por RED y
    # ENLACES. Solo valida y calcula datos EN MEMORIA para las notas; no
    # configura nada en Packet Tracer.
    router_by_lower = {r.lower(): r for r in routers}
    switch_by_lower = {s.lower(): s for s in switches}
    iface_seen = {}          # (router.lower(), interfaz.lower()) -> linea
    switch_claimed_by = {}   # switch.lower() -> nombre de la red que lo reclamo

    def claim_iface(router, iface, lineno):
        key = (router.lower(), iface.lower())
        prev = iface_seen.get(key)
        if prev is not None:
            raise TopologyError(
                f"linea {lineno}: la interfaz '{iface}' de '{router}' ya se uso "
                f"en la linea {prev}.")
        iface_seen[key] = lineno

    for red in redes:
        if red["router_lan"]:
            if red["router_lan"].lower() not in router_by_lower:
                raise TopologyError(
                    f"linea {red['linea']}: el router '{red['router_lan']}' de "
                    f"'RED {red['nombre']}' no esta declarado en ROUTERS:.")
            red["router_lan"] = router_by_lower[red["router_lan"].lower()]
            red["iface_lan"] = red["iface_lan"] or DEFAULT_LAN_IFACE
            claim_iface(red["router_lan"], red["iface_lan"], red["linea"])

        if red["switch_explicit"]:
            sw_canon = switch_by_lower.get(red["switch_name"].lower())
            if sw_canon is None:
                raise TopologyError(
                    f"linea {red['linea']}: el switch '{red['switch_name']}' del "
                    f"conector de 'RED {red['nombre']}' no esta declarado en "
                    f"SWITCHES:.")
            red["switch_name"] = sw_canon
            prev = switch_claimed_by.get(sw_canon.lower())
            if prev is not None and prev != red["nombre"]:
                raise TopologyError(
                    f"linea {red['linea']}: el switch '{sw_canon}' ya fue asignado "
                    f"a la red '{prev}' mediante conector; no puede reutilizarse "
                    f"en '{red['nombre']}'.")
            switch_claimed_by[sw_canon.lower()] = red["nombre"]

        if red["direct"]:
            if len(red["pcs"]) != 1:
                raise TopologyError(
                    f"linea {red['linea']}: 'RED {red['nombre']}' usa conexion "
                    f"directa (sin switch) pero tiene {len(red['pcs'])} "
                    f"dispositivo(s); debe tener exactamente 1.")
            pc_name = red["pcs"][0]["nombre"]
            if pc_name.lower() != red["_pending_direct_pc"].lower():
                raise TopologyError(
                    f"linea {red['linea']}: el conector de 'RED {red['nombre']}' "
                    f"nombra '{red['_pending_direct_pc']}' pero la PC declarada es "
                    f"'{pc_name}'.")

    for enl in enlaces:
        for key in ("r1", "r2"):
            name = enl[key]
            if name.lower() not in router_by_lower:
                raise TopologyError(
                    f"linea {enl['linea']}: el router '{name}' del enlace no esta "
                    f"declarado en ROUTERS:.")
            enl[key] = router_by_lower[name.lower()]  # nombre canonico
        claim_iface(enl["r1"], enl["if1"], enl["linea"])
        claim_iface(enl["r2"], enl["if2"], enl["linea"])
        net = enl["network"]
        enl["ip1"] = str(net.network_address + 1)
        enl["ip2"] = str(net.network_address + 2)
        enl["mascara"] = str(net.netmask)
        enl["prefixlen"] = net.prefixlen

    return {"routers": routers, "switches": switches,
            "router_models": router_models, "switch_models": switch_models,
            "redes": redes, "enlaces": enlaces}


def compute_grouped_layout(parsed, coords, catalog):
    """
    Devuelve (placements, notes, iface_notes, link_notes, warnings).
        placements:  [{category, model, nombre, x, y, ip?}]  en orden de colocacion
        notes:       [{texto, red, x, y}]                     notas CIDR (como antes)
        iface_notes: [{router, nombre, ip, mascara, x, y, texto}]
                     una por interfaz de router (LAN de una red, o de un
                     enlace punto a punto) -- SOLO calculo/registro, no se
                     configura ninguna IP real en Packet Tracer.
        link_notes:  [{r1, if1, r2, if2, cidr, ip1, ip2, mascara, x, y, texto}]
                     una por enlace punto a punto, con el CIDR completo en
                     el punto medio entre los dos routers. Si 2+ enlaces
                     comparten el mismo par de routers, esta lista y
                     iface_notes reciben el MISMO offset perpendicular
                     escalonado (ver _perp_unit) para que no colisionen.
    Una columna por red (switch arriba, PCs en cuadricula debajo); routers y
    switches sobrantes en filas superiores compartidas; notas en una banda
    reservada encima de todo.
    """
    x0, y0 = coords["canvas"]["top_left"]
    x1, y1 = coords["canvas"]["bottom_right"]
    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)

    routers = parsed["routers"]
    switches = parsed["switches"]
    redes = parsed["redes"]
    n_net = len(redes)

    # Resolucion de modelo POR DISPOSITIVO (antes era una unica resolucion
    # global para todos los routers y otra para todos los switches). Cada
    # router/switch puede pedir su propio modelo via el bloque agrupado
    # "MODELO: nombre, nombre" (parsed["router_models"]/["switch_models"]);
    # si no pidio ninguno, resolve_model() cae al default del catalogo,
    # exactamente como antes. Se cachea por modelo pedido para no repetir
    # resolucion ni duplicar mensajes de error.
    router_models = parsed.get("router_models", {})
    switch_models = parsed.get("switch_models", {})
    errors = []
    model_cache = {}

    def resolve_for(category, name, explicit_models):
        requested = explicit_models.get(name)
        key = (category, requested)
        if key not in model_cache:
            model_cache[key] = resolve_model(category, requested, catalog, errors)
        return model_cache[key]

    for name in routers:
        resolve_for("router", name, router_models)
    for name in switches:
        resolve_for("switch", name, switch_models)
    if errors:
        raise TopologyError("; ".join(errors))

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

    # Switches ya reclamados por un conector explicito 'ROUTER-SWITCH'
    # (parse_grouped) quedan fuera del reparto posicional y de los
    # "sobrantes". Necesitan switch por posicion las redes SIN conector
    # explicito y SIN conexion directa (conector 'ROUTER-PC').
    claimed_switches = {r["switch_name"] for r in redes if r["switch_explicit"]}
    needs_switch = [r for r in redes if not r["switch_explicit"] and not r["direct"]]
    leftover_switches = [s for s in switches if s not in claimed_switches]
    positional_switches = leftover_switches[:len(needs_switch)]
    extra_switches = leftover_switches[len(needs_switch):]
    if needs_switch and len(positional_switches) < len(needs_switch):
        warnings.append(f"hay {len(needs_switch)} red(es) sin switch explicito pero "
                        f"solo {len(positional_switches)} switch(es) libre(s): esas "
                        f"columnas quedan sin switch.")

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
        placements.append({"category": "router",
                           "model": resolve_for("router", name, router_models),
                           "nombre": name, "x": clamp(round(x), x0, x1), "y": router_y})

    # Posicion final de cada router, para calcular notas de interfaz mas abajo.
    router_xy = {p["nombre"]: (p["x"], p["y"])
                for p in placements if p["category"] == "router"}
    iface_notes = []

    # Switches sobrantes
    for x, name in zip(spread(len(extra_switches), x0, x1), extra_switches):
        placements.append({"category": "switch",
                           "model": resolve_for("switch", name, switch_models),
                           "nombre": name, "x": clamp(round(x), x0, x1),
                           "y": extra_switch_y})

    col_centers = spread(n_net, x0, x1)
    col_w = (x1 - x0) / n_net if n_net else (x1 - x0)
    if n_net > 1 and col_w < COL_GAP_MIN + END_DX:
        warnings.append(f"{n_net} columnas en {x1 - x0}px (~{round(col_w)}px cada una): "
                        f"las redes pueden tocarse.")

    positional_iter = iter(positional_switches)
    for i, red in enumerate(redes):
        cx = col_centers[i]
        if not red["switch_explicit"] and not red["direct"]:
            red["switch_name"] = next(positional_iter, None)
        # si switch_explicit, "switch_name" ya viene fijado y validado desde
        # el parser; si direct, se queda en None (a proposito, sin switch).

        if red["switch_name"]:
            placements.append({"category": "switch",
                               "model": resolve_for("switch", red["switch_name"], switch_models),
                               "nombre": red["switch_name"],
                               "x": clamp(round(cx), x0, x1), "y": switch_y})

        net = red["network"]
        mascara = str(net.netmask)
        gateway = str(net.network_address + 1)   # .1 reservado como gateway

        pcs = red["pcs"]
        per_row = max(1, int(col_w // END_DX))
        per_row = min(per_row, len(pcs)) or 1
        direct_pc_xy = None
        for k, pc in enumerate(pcs):
            ccol = k % per_row
            crow = k // per_row
            px = cx + (ccol - (per_row - 1) / 2) * END_DX
            py = pc_y_start + crow * END_DY
            pcx, pcy = clamp(round(px), x0, x1), clamp(round(py), y0, y1)
            placements.append({"category": "end_device", "model": pc["modelo"],
                               "nombre": pc["nombre"], "ip": pc["ip"],
                               "mascara": mascara, "gateway": gateway,
                               "x": pcx, "y": pcy})
            if red["direct"]:
                direct_pc_xy = (pcx, pcy)

        notes.append({"texto": red["cidr"], "red": red["nombre"],
                      "x": clamp(round(cx), x0, x1), "y": notes_y})

        # Nota de la interfaz LAN del router que sirve esta red (si se
        # declaro con 'RED ...: CIDR ROUTER [IFAZ]' o con un conector
        # 'ROUTER-...'). Solo calculo/registro; no configura ninguna IP real.
        if red["router_lan"]:
            rxy = router_xy.get(red["router_lan"])
            neighbor = None
            if rxy is None:
                warnings.append(f"RED {red['nombre']}: el router '{red['router_lan']}' "
                                f"no se pudo ubicar; se omite su nota de interfaz.")
            elif red["direct"]:
                # Conexion directa (conector 'ROUTER-PC'): el "vecino" para
                # orientar la nota es la PC unica de esta red, no un switch.
                if direct_pc_xy is None:
                    warnings.append(f"RED {red['nombre']}: conexion directa sin PC "
                                    f"ubicada; se omite la nota de interfaz.")
                else:
                    neighbor = direct_pc_xy
            elif not red["switch_name"]:
                warnings.append(f"RED {red['nombre']}: no hay switch en esta columna; "
                                f"se omite la nota de interfaz LAN de "
                                f"'{red['router_lan']}'.")
            else:
                neighbor = (clamp(round(cx), x0, x1), switch_y)

            if rxy is not None and neighbor is not None:
                ix, iy = calculate_interface_position(rxy, neighbor)
                ix, iy = clamp(ix, x0, x1), clamp(iy, y0, y1)
                last_octet = gateway.rsplit(".", 1)[-1]
                iface_notes.append({
                    "router": red["router_lan"], "nombre": red["iface_lan"],
                    "ip": gateway, "mascara": mascara, "x": ix, "y": iy,
                    "texto": f"{red['iface_lan']} .{last_octet}/{net.prefixlen}",
                })

    # Notas de los enlaces punto a punto ('ENLACES:'): 2 notas de interfaz
    # (una por extremo, como antes) + 1 nota de red nueva en el punto medio
    # con el CIDR completo. Cuando 2+ enlaces comparten el mismo par de
    # routers (enlaces duplicados) sus notas caerian todas en el mismo
    # punto; se agrupan por par de routers y se les aplica UN offset
    # perpendicular escalonado por enlace, compartido entre sus 3 notas
    # (las 2 de interfaz + la de punto medio quedan alineadas entre si).
    # Solo calculo/registro, no se configura ninguna IP real.
    link_notes = []
    enlaces_by_pair = {}
    for enl in parsed.get("enlaces", []):
        enlaces_by_pair.setdefault(frozenset((enl["r1"], enl["r2"])), []).append(enl)

    for pair, group in enlaces_by_pair.items():
        a, b = sorted(pair)
        pos_a, pos_b = router_xy.get(a), router_xy.get(b)
        if pos_a is None or pos_b is None:
            warnings.append(f"ENLACES: no se pudo ubicar '{a}' o '{b}'; "
                            f"se omiten sus enlaces.")
            continue
        perp = _perp_unit(pos_b[0] - pos_a[0], pos_b[1] - pos_a[1])
        n = len(group)
        for idx, enl in enumerate(group):
            # stagger = 0 automaticamente cuando n == 1 (enlace unico, sin
            # duplicados): (0 - (1-1)/2) * STEP = 0.
            stagger = (idx - (n - 1) / 2) * LINK_STAGGER_STEP
            sx, sy = round(perp[0] * stagger), round(perp[1] * stagger)

            pos1, pos2 = router_xy[enl["r1"]], router_xy[enl["r2"]]
            ix1, iy1 = calculate_interface_position(pos1, pos2)
            ix2, iy2 = calculate_interface_position(pos2, pos1)
            ix1, iy1 = clamp(ix1 + sx, x0, x1), clamp(iy1 + sy, y0, y1)
            ix2, iy2 = clamp(ix2 + sx, x0, x1), clamp(iy2 + sy, y0, y1)
            last1 = enl["ip1"].rsplit(".", 1)[-1]
            last2 = enl["ip2"].rsplit(".", 1)[-1]
            iface_notes.append({"router": enl["r1"], "nombre": enl["if1"],
                                "ip": enl["ip1"], "mascara": enl["mascara"],
                                "x": ix1, "y": iy1,
                                "texto": f"{enl['if1']} .{last1}/{enl['prefixlen']}"})
            iface_notes.append({"router": enl["r2"], "nombre": enl["if2"],
                                "ip": enl["ip2"], "mascara": enl["mascara"],
                                "x": ix2, "y": iy2,
                                "texto": f"{enl['if2']} .{last2}/{enl['prefixlen']}"})

            mx = round((pos1[0] + pos2[0]) / 2) + sx
            my = round((pos1[1] + pos2[1]) / 2) + sy
            mx, my = clamp(mx, x0, x1), clamp(my, y0, y1)
            link_notes.append({"r1": enl["r1"], "if1": enl["if1"],
                               "r2": enl["r2"], "if2": enl["if2"],
                               "cidr": enl["cidr"], "ip1": enl["ip1"],
                               "ip2": enl["ip2"], "mascara": enl["mascara"],
                               "x": mx, "y": my, "texto": enl["cidr"]})

    return placements, notes, iface_notes, link_notes, warnings


def build_grouped_record(text, placements, notes, iface_notes, link_notes,
                         redes, coords, when):
    # Agrupa las notas de interfaz ya colocadas por router, para anexarlas
    # a su entrada en 'dispositivos' (solo registro; no toca Packet Tracer).
    ifaces_by_router = {}
    for n in iface_notes:
        ifaces_by_router.setdefault(n["router"], []).append({
            "nombre": n["nombre"], "ip": n["ip"], "mascara": n["mascara"],
            "posicion": [n["x"], n["y"]],
        })

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
        if p["category"] == "router" and p["nombre"] in ifaces_by_router:
            d["interfaces"] = ifaces_by_router[p["nombre"]]
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
        "enlaces": [{"r1": n["r1"], "if1": n["if1"], "r2": n["r2"], "if2": n["if2"],
                    "cidr": n["cidr"], "ip1": n["ip1"], "ip2": n["ip2"],
                    "mascara": n["mascara"],
                    "nota_red": {"texto": n["texto"], "posicion": [n["x"], n["y"]]}}
                   for n in link_notes],
    }


def print_grouped_plan(parsed, placements, cabling_plan, notes, iface_notes,
                       link_notes, pcs_to_cfg, ip_missing, warnings, dry_run):
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
        if red.get("switch_name"):
            sw = red["switch_name"]
        elif red.get("direct"):
            sw = f"(directo a {red.get('router_lan') or '?'})"
        else:
            sw = "(sin switch)"
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
    print("  2) Renombrar labels (nombre debajo del icono; NO el hostname CLI)")
    print("     [!] EXPERIMENTAL: offset confirmado a mano solo para router (38px);")
    print("         switch/end_device usan el mismo valor de arranque, sin confirmar:")
    for p in placements:
        oy = rename_label.LABEL_OFFSET_Y.get(p["category"], rename_label.DEFAULT_OFFSET_Y)
        ly = round(p["y"] + oy)
        print(f'     {p["nombre"]:<10} {p["category"]:<11} label en '
              f'({p["x"]:>5}, {ly:>5})  (offset {oy}px)')
    print("-" * 72)
    print("  3) Cablear ENLACES (router-router)")
    print("     [!] EXPERIMENTAL: el CALCULO del indice esta listo, pero la mecanica")
    print("         del clic en Packet Tracer todavia NO esta confirmada a mano --")
    print("         por ahora este paso solo CALCULA, no mueve el mouse:")
    if not cabling_plan:
        print("     (ninguno: no hay bloque 'ENLACES:', o falta 'router_interfaces' "
              "en el catalogo)")
    else:
        for c in cabling_plan:
            print(f'     {c["r1"]:<10} interfaz #{c["idx1"]:<2} ({c["if1"]})  <->  '
                  f'{c["r2"]:<10} interfaz #{c["idx2"]:<2} ({c["if2"]})   [{c["cidr"]}]')
    print("-" * 72)
    print("  4) Notas (CIDR por red)  [clic de foco -> 'n' -> clic -> texto -> Escape]:")
    for n in notes:
        print(f'     "{n["texto"]}"  -> ({n["x"]:>5}, {n["y"]:>5})   [{n["red"]}]')
    print("-" * 72)
    print("  5) Notas de interfaz (LAN de router + enlaces)  [solo texto, NO configura IP]:")
    if not iface_notes:
        print("     (ninguna: no hay 'RED ... ROUTER' ni bloque 'ENLACES:')")
    else:
        for n in iface_notes:
            print(f'     {n["router"]:<10} "{n["texto"]}"  -> ({n["x"]:>5}, {n["y"]:>5})')
    print("-" * 72)
    print("  6) Notas de enlace (CIDR completo, punto medio)  [solo texto, NO configura IP]:")
    if not link_notes:
        print("     (ninguna: no hay bloque 'ENLACES:')")
    else:
        for n in link_notes:
            label = f'{n["r1"]}-{n["r2"]}'
            print(f'     {label:<12} "{n["texto"]}"  -> ({n["x"]:>5}, {n["y"]:>5})')
    print("-" * 72)
    print("  7) Configuracion IP de las PCs  (DESPUES de colocar todo y las notas):")
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
        placements, notes, iface_notes, link_notes, warnings = compute_grouped_layout(
            parsed, coords, catalog)
    except TopologyError as e:
        print()
        print("ERROR: no se pudo resolver el layout:")
        print(f"  - {e}")
        sys.exit(1)

    # Plan de cableado de ENLACES (router-router). Solo calculo por ahora --
    # la mecanica del clic en Packet Tracer todavia no esta confirmada a
    # mano (ver compute_cabling_plan / cable_link.py pendiente).
    cabling_plan, cabling_warnings = compute_cabling_plan(parsed, placements, catalog)
    warnings = warnings + cabling_warnings

    # Paso 7 (config IP): se hace tras colocar todo. Aqui solo se comprueba
    # que ip_config_coords.json esta calibrado; si no, se omite con aviso.
    pcs_to_cfg = [p for p in placements
                  if p["category"] == "end_device" and p.get("ip")]
    ip_data = coords_io.load_coords(IP_CONFIG_COORDS_PATH)
    ip_missing = [k for k in configure_ip.REQUIRED_COORDS if ip_data.get(k) is None]

    print_grouped_plan(parsed, placements, cabling_plan, notes, iface_notes,
                       link_notes, pcs_to_cfg, ip_missing, warnings, args.dry_run)
    if args.dry_run:
        return

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    countdown(max(0, args.countdown))

    # Punto FIJO y neutro para recuperar el foco de la ventana entre nota y
    # nota. NO se reutiliza la posicion de cada nota: si dos notas quedan
    # cerca (p. ej. una nota de interfaz junto a la nota CIDR de su columna),
    # el cuadro de texto de la nota anterior puede seguir abierto y tapar la
    # coordenada de la siguiente; el clic de foco caeria DENTRO de ese
    # cuadro en vez de en lienzo vacio, y la 'n' de la proxima nota se
    # escribiria como caracter literal en vez de activar Place Note Mode
    # (bug real: notas encadenadas dentro de un mismo cuadro de texto).
    # La esquina superior izquierda + margen queda libre porque el layout
    # arranca sus columnas con medio paso de margen (ver spread()).
    cx0, cy0 = coords["canvas"]["top_left"]
    cx1, cy1 = coords["canvas"]["bottom_right"]
    note_focus_xy = (min(cx0, cx1) + 8, min(cy0, cy1) + 8)

    placed_ok = 0
    renamed_ok = 0
    notes_ok = 0
    iface_notes_ok = 0
    link_notes_ok = 0
    ip_ok = 0
    ip_fail = 0
    aborted = False
    try:
        for p in placements:
            place_device(coords, p["model"], p["x"], p["y"],
                         args.pause, args.filter_delay)
            placed_ok += 1
        # Paso adicional: renombrar el label visual (no el hostname) de cada
        # dispositivo con su nombre declarado en la topologia. EXPERIMENTAL:
        # offset confirmado a mano solo para router; switch/end_device usan
        # el mismo valor de arranque (ver rename_label.LABEL_OFFSET_Y).
        for p in placements:
            rename_label.rename_label(p["x"], p["y"], p["nombre"],
                                      category=p["category"], pause=args.pause)
            renamed_ok += 1
        # Cableado de ENLACES: el CALCULO (compute_cabling_plan) ya esta
        # listo, pero la mecanica del clic en Packet Tracer todavia no esta
        # confirmada a mano -- no se mueve el mouse para esto todavia.
        if cabling_plan:
            print(f"\n  [!] Cableado automatico pendiente: {len(cabling_plan)} "
                  f"enlace(s) calculados, 0 cableados (falta confirmar la mecanica "
                  f"del clic en Packet Tracer; ver print del plan arriba).")
        for n in notes:
            # focus_xy recupera el foco de la ventana entre nota y nota
            # (tras el Escape anterior el foco sale de Packet Tracer). Usa
            # el punto neutro fijo, NO la posicion de la nota (ver comentario
            # arriba de note_focus_xy).
            add_note.place_note(n["texto"], n["x"], n["y"],
                                pause=args.pause, focus_xy=note_focus_xy)
            notes_ok += 1
        # Paso adicional: notas de interfaz (LAN de router + enlaces). Mismo
        # mecanismo que las notas CIDR de arriba; NO configura ninguna IP
        # real, solo coloca el texto en el lienzo.
        for n in iface_notes:
            add_note.place_note(n["texto"], n["x"], n["y"],
                                pause=args.pause, focus_xy=note_focus_xy)
            iface_notes_ok += 1
        # Paso adicional: notas de enlace (CIDR completo en el punto medio
        # de cada 'ENLACES:'). Mismo mecanismo que las notas de arriba.
        for n in link_notes:
            add_note.place_note(n["texto"], n["x"], n["y"],
                                pause=args.pause, focus_xy=note_focus_xy)
            link_notes_ok += 1
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
    print(f"  Labels renom.: {renamed_ok} / {len(placements)}")
    print(f"  Notas CIDR  : {notes_ok} / {len(notes)}")
    print(f"  Notas iface : {iface_notes_ok} / {len(iface_notes)}")
    print(f"  Notas enlace: {link_notes_ok} / {len(link_notes)}")
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
            text, placements[:placed_ok], notes[:notes_ok],
            iface_notes[:iface_notes_ok], link_notes[:link_notes_ok],
            parsed["redes"], coords, now)
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
