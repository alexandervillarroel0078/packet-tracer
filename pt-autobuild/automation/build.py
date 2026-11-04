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

import datetime
import json
import os
import time

from core import coords as coords_io
from core import dpi_aware  # noqa: F401  DEBE importarse antes de pyautogui (fija DPI awareness)
from core import paths
from core.errors import CancelledError, NotCalibratedError
from core.paths import CATALOG_PATH

import pyautogui

from automation import add_note, common, configure_ip, rename_label  # noqa: E402

from core.topology import (  # noqa: E402
    CAT_INFO, CAT_ORDER, TopologyError, build_grouped_record, build_topology_record,
    compute_cabling_plan, compute_grouped_layout, compute_layout, is_grouped_syntax,
    load_catalog, parse_grouped, parse_topology, resolve_model)


# --- Carga de coordenadas ------------------------------------------------
def load_coords(log=None):
    """Lee coords.json y comprueba que esta completo. NotCalibratedError si falta algo."""
    log = common.get_log(log)
    path = paths.COORDS_PATH
    if not os.path.exists(path):
        raise NotCalibratedError(f"no existe {path}. Calibra primero (pestana Calibracion).")
    with open(path, "r", encoding="utf-8") as f:
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
        raise NotCalibratedError(
            f"faltan coordenadas en {path}: " + ", ".join(missing)
            + ". Calibra en la pestana Calibracion.")

    saved = coords.get("screen_size")
    current = list(pyautogui.size())
    if saved and saved != current:
        log(f"  Aviso: la resolucion actual {tuple(current)} no coincide con la de")
        log(f"  la calibracion {tuple(saved)}. Las coordenadas pueden fallar.")
    return coords


def start_countdown(seconds, log=None, cancel=None):
    """Cuenta regresiva visible antes de tomar el control del mouse."""
    log = common.get_log(log)
    common.countdown(max(0, seconds), log, cancel,
                     text="Empezando en {i}...  (cambia el foco a Packet Tracer)")
    log("  Colocando dispositivos...")


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


def print_plan(resolved, placements, warnings, dry_run, log=None):
    log = common.get_log(log)
    log("=" * 72)
    log("  pt-autobuild :: PLAN DE COLOCACION")
    log("=" * 72)
    log(f"  DPI awareness: {dpi_aware.STATUS}")
    _ok, _msg = dpi_aware.verify()
    log(f"  {'' if _ok else '[!] '}{_msg}")
    log("-" * 72)
    total = 0
    for cat in CAT_ORDER:
        for r in [g for g in resolved if g["category"] == cat]:
            _, label = CAT_INFO[cat]
            log(f"  {label:<11} x {r['count']:<3}  modelo {r['model']}")
            total += r["count"]
    log(f"  Total: {total} dispositivos")
    log("-" * 72)
    for idx, p in enumerate(placements, 1):
        _, label = CAT_INFO[p["category"]]
        log(f"  {idx:>3}. {label:<11} {p['model']:<12} -> ({p['x']:>5}, {p['y']:>5})")
    if warnings:
        log("-" * 72)
        for w in warnings:
            log(f"  [!] {w}")
    if dry_run:
        log("-" * 72)
        log("  DRY-RUN: no se movera el mouse.")
    log("=" * 72)


def print_catalog(catalog, log=None):
    log = common.get_log(log)
    log("  device_catalog.json")
    log("-" * 50)
    for cat in CAT_ORDER:
        cat_key, _ = CAT_INFO[cat]
        default = catalog["defaults"].get(cat_key, "(sin default)")
        log(f"  {cat_key.replace('_', ' ')}  (default: {default})")
        for m in catalog[cat_key]:
            log(f"    - {m}")


def save_topology_record(record, when, log=None):
    log = common.get_log(log)
    """
    Escribe dos archivos junto a build.py:
      - topologia_<fecha>_<hora>.json  (historico, no se sobrescribe)
      - topologia_actual.json          (siempre la ultima ejecucion)
    """
    stamp = when.strftime("%Y-%m-%d_%H-%M")
    os.makedirs(paths.TOPOLOGY_HISTORY_DIR, exist_ok=True)
    stamped = os.path.join(paths.TOPOLOGY_HISTORY_DIR, f"topologia_{stamp}.json")
    for path in (stamped, paths.TOPOLOGY_ACTUAL_PATH):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
            f.write("\n")
    log(f"  Registro guardado: data/topology/history/{os.path.basename(stamped)}")
    log("                     data/topology/topologia_actual.json")


def print_grouped_plan(parsed, placements, cabling_plan, notes, iface_notes,
                       link_notes, pcs_to_cfg, ip_missing, warnings, dry_run, log=None):
    log = common.get_log(log)
    log("=" * 72)
    log("  pt-autobuild :: PLAN DE COLOCACION (sintaxis por redes)")
    log("=" * 72)
    log(f"  DPI awareness: {dpi_aware.STATUS}")
    _ok, _msg = dpi_aware.verify()
    log(f"  {'' if _ok else '[!] '}{_msg}")
    log("-" * 72)
    by_name = {p["nombre"]: p for p in placements}
    if parsed["routers"]:
        log(f"  Routers : {', '.join(parsed['routers'])}")
    for red in parsed["redes"]:
        if red.get("switch_name"):
            sw = red["switch_name"]
        elif red.get("direct"):
            sw = f"(directo a {red.get('router_lan') or '?'})"
        else:
            sw = "(sin switch)"
        log(f"  {red['nombre']}  {red['cidr']}   switch {sw}")
        for pc in red["pcs"]:
            p = by_name.get(pc["nombre"], {})
            log(f"     {pc['nombre']:<10} {(pc['ip'] or '(sin ip)'):<15} "
                  f"-> ({p.get('x', '?')}, {p.get('y', '?')})")
    log("-" * 72)
    log("  1) Orden de colocacion:")
    for idx, p in enumerate(placements, 1):
        log(f"  {idx:>3}. {p['category']:<11} {p['model']:<12} {p['nombre']:<10} "
              f"-> ({p['x']:>5}, {p['y']:>5})")
    log("-" * 72)
    log("  2) Renombrar labels (nombre debajo del icono; NO el hostname CLI)")
    log("     [!] EXPERIMENTAL: offset confirmado a mano solo para router (38px);")
    log("         switch/end_device usan el mismo valor de arranque, sin confirmar:")
    for p in placements:
        oy = rename_label.LABEL_OFFSET_Y.get(p["category"], rename_label.DEFAULT_OFFSET_Y)
        ly = round(p["y"] + oy)
        log(f'     {p["nombre"]:<10} {p["category"]:<11} label en '
              f'({p["x"]:>5}, {ly:>5})  (offset {oy}px)')
    log("-" * 72)
    log("  3) Cablear ENLACES (router-router)")
    log("     [!] EXPERIMENTAL: el CALCULO del indice esta listo, pero la mecanica")
    log("         del clic en Packet Tracer todavia NO esta confirmada a mano --")
    log("         por ahora este paso solo CALCULA, no mueve el mouse:")
    if not cabling_plan:
        log("     (ninguno: no hay bloque 'ENLACES:', o falta 'router_interfaces' "
              "en el catalogo)")
    else:
        for c in cabling_plan:
            log(f'     {c["r1"]:<10} interfaz #{c["idx1"]:<2} ({c["if1"]})  <->  '
                  f'{c["r2"]:<10} interfaz #{c["idx2"]:<2} ({c["if2"]})   [{c["cidr"]}]')
    log("-" * 72)
    log("  4) Notas (CIDR por red)  [clic de foco -> 'n' -> clic -> texto -> Escape]:")
    for n in notes:
        log(f'     "{n["texto"]}"  -> ({n["x"]:>5}, {n["y"]:>5})   [{n["red"]}]')
    log("-" * 72)
    log("  5) Notas de interfaz (LAN de router + enlaces)  [solo texto, NO configura IP]:")
    if not iface_notes:
        log("     (ninguna: no hay 'RED ... ROUTER' ni bloque 'ENLACES:')")
    else:
        for n in iface_notes:
            log(f'     {n["router"]:<10} "{n["texto"]}"  -> ({n["x"]:>5}, {n["y"]:>5})')
    log("-" * 72)
    log("  6) Notas de enlace (CIDR completo, punto medio)  [solo texto, NO configura IP]:")
    if not link_notes:
        log("     (ninguna: no hay bloque 'ENLACES:')")
    else:
        for n in link_notes:
            label = f'{n["r1"]}-{n["r2"]}'
            log(f'     {label:<12} "{n["texto"]}"  -> ({n["x"]:>5}, {n["y"]:>5})')
    log("-" * 72)
    log("  7) Configuracion IP de las PCs  (DESPUES de colocar todo y las notas):")
    if ip_missing:
        log(f"     [!] SE OMITE: faltan puntos en data/ip_config_coords.json: "
              f"{', '.join(ip_missing)}")
        log("         Calibra con:  python configure_ip.py --calibrate")
    elif not pcs_to_cfg:
        log("     (no hay PCs con IP asignada)")
    else:
        for p in pcs_to_cfg:
            log(f"     {p['nombre']:<10} IP {p['ip']:<15} mask {p['mascara']:<15} "
                  f"gw {p['gateway']}   (doble clic en {p['x']},{p['y']})")
    if warnings:
        log("-" * 72)
        for w in warnings:
            log(f"  [!] {w}")
    if dry_run:
        log("-" * 72)
        log("  DRY-RUN: no se movera el mouse ni se escribira el registro.")
    log("=" * 72)


def run_grouped(text, catalog, args, log=None, cancel=None):
    """Camino de la sintaxis por redes. No toca el camino de la sintaxis simple.

    args: BuildOptions (dry_run, countdown, pause, filter_delay)."""
    log = common.get_log(log)
    try:
        parsed = parse_grouped(text)
    except TopologyError as e:
        raise TopologyError(f"la topologia no es valida (no se coloco nada): {e}") from e

    coords = load_coords(log)
    try:
        placements, notes, iface_notes, link_notes, warnings = compute_grouped_layout(
            parsed, coords, catalog)
    except TopologyError as e:
        raise TopologyError(f"no se pudo resolver el layout: {e}") from e

    # Plan de cableado de ENLACES (router-router). Solo calculo por ahora --
    # la mecanica del clic en Packet Tracer todavia no esta confirmada a
    # mano (ver compute_cabling_plan / cable_link.py pendiente).
    cabling_plan, cabling_warnings = compute_cabling_plan(parsed, placements, catalog)
    warnings = warnings + cabling_warnings

    # Paso 7 (config IP): se hace tras colocar todo. Aqui solo se comprueba
    # que ip_config_coords.json esta calibrado; si no, se omite con aviso.
    pcs_to_cfg = [p for p in placements
                  if p["category"] == "end_device" and p.get("ip")]
    ip_data = coords_io.load_coords(paths.IP_CONFIG_COORDS_PATH)
    ip_missing = [k for k in configure_ip.REQUIRED_COORDS if ip_data.get(k) is None]

    print_grouped_plan(parsed, placements, cabling_plan, notes, iface_notes,
                       link_notes, pcs_to_cfg, ip_missing, warnings, args.dry_run, log)
    if args.dry_run:
        return None

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    start_countdown(args.countdown, log, cancel)

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
            common.check_cancel(cancel)
            place_device(coords, p["model"], p["x"], p["y"],
                         args.pause, args.filter_delay)
            placed_ok += 1
        # Paso adicional: renombrar el label visual (no el hostname) de cada
        # dispositivo con su nombre declarado en la topologia. EXPERIMENTAL:
        # offset confirmado a mano solo para router; switch/end_device usan
        # el mismo valor de arranque (ver rename_label.LABEL_OFFSET_Y).
        for p in placements:
            common.check_cancel(cancel)
            rename_label.rename_label(p["x"], p["y"], p["nombre"],
                                      category=p["category"], pause=args.pause)
            renamed_ok += 1
        # Cableado de ENLACES: el CALCULO (compute_cabling_plan) ya esta
        # listo, pero la mecanica del clic en Packet Tracer todavia no esta
        # confirmada a mano -- no se mueve el mouse para esto todavia.
        if cabling_plan:
            log(f"\n  [!] Cableado automatico pendiente: {len(cabling_plan)} "
                  f"enlace(s) calculados, 0 cableados (falta confirmar la mecanica "
                  f"del clic en Packet Tracer; ver print del plan arriba).")
        for n in notes:
            common.check_cancel(cancel)
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
            common.check_cancel(cancel)
            add_note.place_note(n["texto"], n["x"], n["y"],
                                pause=args.pause, focus_xy=note_focus_xy)
            iface_notes_ok += 1
        # Paso adicional: notas de enlace (CIDR completo en el punto medio
        # de cada 'ENLACES:'). Mismo mecanismo que las notas de arriba.
        for n in link_notes:
            common.check_cancel(cancel)
            add_note.place_note(n["texto"], n["x"], n["y"],
                                pause=args.pause, focus_xy=note_focus_xy)
            link_notes_ok += 1
    except pyautogui.FailSafeException:
        aborted = True
        log("\n  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except CancelledError:
        aborted = True
        log("\n  Cancelado por el usuario.")
    except KeyboardInterrupt:
        aborted = True
        log("\n  Interrumpido por el usuario.")

    # --- Paso 3: configurar IP/mascara/gateway de cada PC ---------------
    if not aborted and pcs_to_cfg:
        log("")
        if ip_missing:
            log(f"  [!] No se configuran IPs: faltan puntos calibrados "
                  f"({', '.join(ip_missing)}).")
            log("      Calibra la ventana IP en la pestana Calibracion.")
        else:
            log(f"  Configurando IP de {len(pcs_to_cfg)} PC(s)...")
            for p in pcs_to_cfg:
                try:
                    common.check_cancel(cancel)
                    configure_ip.apply_ip(ip_data, p["x"], p["y"], p["ip"],
                                          p["mascara"], p["gateway"],
                                          pause=args.pause)
                    ip_ok += 1
                    log(f"    OK    {p['nombre']:<10} {p['ip']}/{p['mascara']} "
                          f"gw {p['gateway']}")
                except CancelledError:
                    aborted = True
                    log("\n  Cancelado por el usuario.")
                    break
                except pyautogui.FailSafeException:
                    aborted = True
                    log("\n  ABORTADO por failsafe durante la configuracion IP.")
                    break
                except KeyboardInterrupt:
                    aborted = True
                    log("\n  Interrumpido durante la configuracion IP.")
                    break
                except Exception as e:  # noqa: BLE001  (una PC falla -> seguir con las demas)
                    ip_fail += 1
                    log(f"    FALLO {p['nombre']:<10} ({type(e).__name__}: {e})")

    try:
        w, h = pyautogui.size()
        pyautogui.moveTo(w // 2, h // 2)
    except Exception:  # noqa: BLE001
        pass

    log("")
    log("=" * 72)
    log("  RESUMEN")
    log("=" * 72)
    log(f"  Dispositivos: {placed_ok} / {len(placements)}")
    log(f"  Labels renom.: {renamed_ok} / {len(placements)}")
    log(f"  Notas CIDR  : {notes_ok} / {len(notes)}")
    log(f"  Notas iface : {iface_notes_ok} / {len(iface_notes)}")
    log(f"  Notas enlace: {link_notes_ok} / {len(link_notes)}")
    if pcs_to_cfg:
        if ip_missing:
            log(f"  Config IP   : omitida (falta calibracion) / {len(pcs_to_cfg)} PCs")
        else:
            log(f"  Config IP   : {ip_ok} OK / {ip_fail} fallaron / "
                  f"{len(pcs_to_cfg)} PCs")
    if aborted:
        log("  Ejecucion incompleta (abortada).")
    log("  Recuerda: los cables se conectan manualmente.")
    log("=" * 72)

    if placed_ok > 0:
        now = datetime.datetime.now()
        record = build_grouped_record(
            text, placements[:placed_ok], notes[:notes_ok],
            iface_notes[:iface_notes_ok], link_notes[:link_notes_ok],
            parsed["redes"], coords, now)
        try:
            save_topology_record(record, now, log)
        except OSError as e:  # noqa: BLE001
            log(f"  [!] No se pudo guardar el registro de topologia: {e}")
    return {"aborted": aborted, "placed": placed_ok, "total": len(placements)}


class BuildOptions:
    """Opciones de ejecucion de build_topology (dry_run=True por defecto)."""

    def __init__(self, dry_run=True, countdown=5, pause=0.4, filter_delay=0.4):
        self.dry_run = dry_run
        self.countdown = max(0, int(countdown))
        self.pause = pause
        self.filter_delay = filter_delay


def list_models(catalog_path=None, log=None):
    """Muestra el catalogo de modelos disponibles."""
    print_catalog(load_catalog(catalog_path or CATALOG_PATH), log)


def build_topology(text, *, dry_run=True, pause=0.4, filter_delay=0.4, countdown=5,
                   catalog_path=None, log=None, cancel=None):
    """
    Coloca una topologia en Packet Tracer (sintaxis simple "3 routers, 2 switches, 5 PC" o
    por redes agrupadas). dry_run=True (por defecto) solo calcula y muestra el plan: no mueve
    el mouse. Devuelve None en dry-run, o {"aborted", "placed", "total"}.

    Lanza TopologyError (topologia invalida), NotCalibratedError (falta calibrar),
    PTError (otros) y nunca llama a sys.exit(). Cancelar o el failsafe de pyautogui
    detienen la colocacion con un resumen parcial (aborted=True) y guardan lo ya colocado.
    """
    log = common.get_log(log)
    args = BuildOptions(dry_run, countdown, pause, filter_delay)
    catalog = load_catalog(catalog_path or CATALOG_PATH)
    if not str(text).strip():
        raise TopologyError("indica una topologia.")

    # Sintaxis por redes agrupadas (SWITCHES: / ROUTERS: / RED ...).
    # La sintaxis simple ("2 routers, 2 switches, 4 PC") sigue igual, debajo.
    if is_grouped_syntax(text):
        return run_grouped(text, catalog, args, log, cancel)

    groups, warnings = parse_topology(text)
    for w in warnings:
        log(f"  Aviso: {w}")
    if not groups:
        raise TopologyError("no se reconocio ningun dispositivo en la topologia.")

    # Resolver modelos contra el catalogo
    errors = []
    resolved = []
    for g in groups:
        model = resolve_model(g["category"], g["model"], catalog, errors)
        if model is None:
            continue
        resolved.append({"category": g["category"], "model": model, "count": g["count"]})
    if errors:
        raise TopologyError("la topologia no se puede resolver: " + "; ".join(errors))

    coords = load_coords(log)
    placements, layout_warnings = compute_layout(resolved, coords)

    print_plan(resolved, placements, layout_warnings, args.dry_run, log)

    if args.dry_run:
        return None

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0

    start_countdown(args.countdown, log, cancel)

    attempted = {"router": 0, "switch": 0, "end_device": 0}
    placed_ok = 0
    aborted = False
    try:
        for p in placements:
            common.check_cancel(cancel)
            place_device(coords, p["model"], p["x"], p["y"],
                         args.pause, args.filter_delay)
            attempted[p["category"]] += 1
            placed_ok += 1
    except pyautogui.FailSafeException:
        aborted = True
        log("\n  ABORTADO por failsafe (mouse en la esquina superior izquierda).")
    except CancelledError:
        aborted = True
        log("\n  Cancelado por el usuario.")
    except KeyboardInterrupt:
        aborted = True
        log("\n  Interrumpido por el usuario.")

    # mouse a un sitio neutro
    try:
        w, h = pyautogui.size()
        pyautogui.moveTo(w // 2, h // 2)
    except Exception:  # noqa: BLE001
        pass

    log("")
    log("=" * 72)
    log("  RESUMEN")
    log("=" * 72)
    for cat in CAT_ORDER:
        want = sum(r["count"] for r in resolved if r["category"] == cat)
        if want:
            _, label = CAT_INFO[cat]
            log(f"  {label:<11}: {attempted[cat]} / {want} colocados")
    log("-" * 72)
    log(f"  Total intentado: {placed_ok} / {len(placements)}")
    if aborted:
        log("  Ejecucion incompleta (abortada).")
    log("  Recuerda: los cables se conectan manualmente.")
    log("=" * 72)

    # Registro de la topologia resultante (solo si de verdad se coloco algo).
    # Se guardan unicamente los dispositivos efectivamente colocados.
    if placed_ok > 0:
        now = datetime.datetime.now()
        record = build_topology_record(text, placements[:placed_ok], coords, now)
        try:
            save_topology_record(record, now, log)
        except OSError as e:  # noqa: BLE001
            log(f"  [!] No se pudo guardar el registro de topologia: {e}")
    return {"aborted": aborted, "placed": placed_ok, "total": len(placements)}
