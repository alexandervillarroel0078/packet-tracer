"""
cable_link.py - Crea cables (serial, cobre, etc.) entre dos dispositivos en
Cisco Packet Tracer.

Estado: EXPERIMENTAL, pero la mecanica YA fue confirmada a mano:
    clic icono de cable (rayo) -> clic TIPO de cable (sub-paleta) ->
    clic dispositivo1 -> aparece la lista de sus interfaces (desplegada un
    poco a la derecha del clic) -> UN SOLO clic sobre el item deseado (sin
    Enter, sin navegar con teclado) -> clic dispositivo2 -> clic en su item.

    Tambien confirmado: la herramienta de cable QUEDA ARMADA entre un
    cable y el siguiente MIENTRAS sea el MISMO tipo -- no hace falta
    volver a clickear rayo+tipo salvo para el primer cable del run, o
    cuando el tipo cambia respecto al cable anterior (ver cable_all() /
    select_tool). Lo de "mismo tipo" es supuesto por prudencia -- no se
    confirmo a mano que cambiar de tipo tambien deje la seleccion armada.

    El icono del RAYO y la geometria de la lista desplegada (list_offset /
    list_row_height) son GENERICOS: el mismo mecanismo de menu de Packet
    Tracer sea cual sea el tipo de cable elegido en la sub-paleta -- se
    calibran UNA sola vez. Lo unico que cambia por tipo de cable es CUAL
    icono de la sub-paleta clickear (cable_coords.json -> "cable_icons",
    un diccionario {tipo: [x, y]}, ej. {"serial": [...], "copper": [...]}).

Lo que SI falta calibrar en tu maquina (pixeles especificos de tu
resolucion/zoom): la posicion del icono de rayo, la posicion del icono de
CADA tipo de cable que uses en la sub-paleta, y la geometria de la lista
(offset del item 0 + altura de fila). Se capturan en vivo con --calibrate
--tipo <TIPO> (mueve el mouse + ESPACIO), NO se miden en una imagen.

Reutiliza core/:
    dpi_aware    marca el proceso DPI-aware (antes que pyautogui)
    coords       capture_point / load_coords / save_coords
    ptwindow     click_point / park_mouse
    topology     load_topology / find_device (posicion de cada dispositivo)

Uso (desde pt-autobuild/):
    python cable_link.py --calibrate --tipo serial --router R01
    python cable_link.py --calibrate --tipo copper --router R01
        (calibra SOLO el icono de ese tipo en la sub-paleta; el icono del
        rayo y la geometria de la lista, si ya estan calibrados, no se
        vuelven a pedir -- usa --recalibrate para forzarlos de nuevo)
    python cable_link.py R01 3 R04 3 --tipo serial --dry-run
    python cable_link.py R01 3 Sw1 5 --tipo copper --dry-run
    python cable_link.py R01 5 R02 3 --tipo serial --no-select-tool
        (para probar a mano que la herramienta sigue armada de un cable
        anterior DEL MISMO TIPO, sin volver a clickear rayo+tipo)

Los INDICES (3, 3 / 5, 3 arriba) son el resultado YA calculado por
build.compute_menu_index() -- este script no los recalcula, solo hace los
clics. Fuera de --calibrate, este script asume que Packet Tracer no tiene
NADA cableado todavia en los dispositivos indicados (por eso build.py
cablea INMEDIATAMENTE despues de colocar, antes de cualquier nota).

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre pasos.
"""

import argparse
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
from core import coords as coords_io
from core.paths import CABLE_COORDS_PATH, TOPOLOGY_ACTUAL_PATH
from core.topology import load_topology, find_device

try:
    import pyautogui
except ImportError:
    print("ERROR: falta pyautogui. Instala las dependencias con:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

from core import ptwindow  # noqa: E402  (usa pyautogui; va despues del guard)

DEFAULT_TIPO = "serial"
# Genericos al mecanismo de menu de Packet Tracer (NO dependen del tipo de
# cable elegido en la sub-paleta): el icono del rayo y la geometria de la
# lista de interfaces. Lo unico por-tipo es cable_icons[tipo].
BASE_REQUIRED_COORDS = ("cable_icon", "list_offset", "list_row_height")


def _migrate_old_schema(data):
    """Compat: versiones previas guardaban un unico 'serial_icon' suelto en
    vez de 'cable_icons': {'serial': [...]}. Lo migra sin perder nada."""
    if "serial_icon" in data:
        data.setdefault("cable_icons", {}).setdefault("serial", data.pop("serial_icon"))
    return data


def missing_coords(data, tipo):
    """Claves que faltan calibrar para poder cablear con 'tipo'."""
    missing = [k for k in BASE_REQUIRED_COORDS if data.get(k) is None]
    if not data.get("cable_icons", {}).get(tipo):
        missing.append(f"cable_icons.{tipo}")
    return missing


def interface_item_xy(device_pos, index, cable_data):
    """
    (x, y) absolutos del item 'index' (0-based) en la lista de interfaces
    que Packet Tracer despliega al clickear un dispositivo con la
    herramienta de cable activa.

    Formula lineal confirmada a mano: offset FIJO desde el punto donde se
    clickeo el dispositivo, mas 'index' veces la altura de fila (la lista
    es vertical y regular). 'device_pos' es la posicion del icono (la
    misma que build.py uso para colocarlo), no la del item.
    """
    dx, dy = device_pos
    ox, oy = cable_data["list_offset"]
    row_h = cable_data["list_row_height"]
    return (round(dx + ox), round(dy + oy + index * row_h))


def cable_link(pos1, idx1, pos2, idx2, cable_data, *, tipo=DEFAULT_TIPO,
              pause=0.4, list_delay=0.4, select_tool=True):
    """Crea UN cable entre dos dispositivos ya colocados.

    pos1/pos2: (x, y) del icono de cada dispositivo (topologia_actual.json).
    idx1/idx2: indice YA calculado (build.compute_menu_index) de la
    interfaz deseada en CADA dispositivo, en el momento de este cable.
    tipo: clave dentro de cable_data["cable_icons"] (ej. 'serial', 'copper')
    -- decide que icono de la sub-paleta clickear. El resto del mecanismo
    (offset/altura de la lista, secuencia de clics en los dispositivos) es
    el MISMO para cualquier tipo de cable: confirmado a mano que es
    generico al menu de Packet Tracer, no depende del tipo elegido.

    select_tool: True reselecciona rayo + icono del tipo antes de clickear
    los dispositivos (hace falta para el PRIMER cable del run, o cuando el
    tipo cambia respecto al cable anterior). False asume que la
    herramienta sigue armada de un cable anterior DEL MISMO TIPO -- ya
    CONFIRMADO A MANO que Packet Tracer la deja armada entre cables
    consecutivos del mismo tipo, asi que alcanza con False (ahorra 2 clics
    por cable). Ver cable_all() para la orquestacion automatica de esto
    sobre una lista de enlaces (incluyendo el caso de tipos mezclados).

    Asume que pyautogui.FAILSAFE lo gestiona el llamador. No hace cuenta
    regresiva. Propaga FailSafeException / KeyboardInterrupt.
    """
    if select_tool:
        icon = cable_data.get("cable_icons", {}).get(tipo)
        if icon is None:
            raise ValueError(
                f"falta calibrar el icono del tipo de cable '{tipo}' "
                f"(cable_coords.json -> cable_icons.{tipo}); corre "
                f"'python cable_link.py --calibrate --tipo {tipo} --router <NOMBRE>'.")
        ptwindow.click_point(cable_data["cable_icon"], pause)
        ptwindow.click_point(icon, pause)

    ptwindow.click_point((int(pos1[0]), int(pos1[1])), list_delay)  # abre la lista de pos1
    ix1, iy1 = interface_item_xy(pos1, idx1, cable_data)
    ptwindow.click_point((ix1, iy1), pause)

    ptwindow.click_point((int(pos2[0]), int(pos2[1])), list_delay)  # abre la lista de pos2
    ix2, iy2 = interface_item_xy(pos2, idx2, cable_data)
    ptwindow.click_point((ix2, iy2), pause)


def cable_all(links, cable_data, *, tipo=DEFAULT_TIPO, pause=0.4, list_delay=0.4):
    """
    Crea TODOS los cables de 'links', EN ORDEN, con la logica de
    reseleccion de herramienta ya resuelta: reselecciona rayo + icono del
    tipo SOLO en el primer cable del run, y cada vez que el tipo de cable
    cambia respecto al cable anterior; el resto reutiliza la herramienta
    armada (confirmado a mano para cables consecutivos del MISMO tipo; el
    caso de cambio de tipo se asume por prudencia, no esta confirmado a
    mano que la seleccion de tipo tambien quede armada al cambiar).

    links: [{"pos1", "idx1", "pos2", "idx2", "tipo"(opcional)}, ...] --
    mismo formato que produce build.compute_cabling_plan() (mapeando
    r1/r2 a sus posiciones reales antes de llamar esto), mas un 'tipo' por
    link si se necesitan mezclar tipos de cable en el mismo run; si un
    link no trae 'tipo', usa el parametro 'tipo' de este llamado. No
    duplica esta logica en build.py: se reutiliza cable_all() tal cual.

    Propaga FailSafeException / KeyboardInterrupt en el cable que fallo;
    los cables anteriores en la lista ya quedaron hechos. Devuelve cuantos
    se completaron con exito.
    """
    done = 0
    prev_tipo = None
    for i, link in enumerate(links):
        link_tipo = link.get("tipo", tipo)
        select_tool = (i == 0) or (link_tipo != prev_tipo)
        cable_link(link["pos1"], link["idx1"], link["pos2"], link["idx2"],
                  cable_data, tipo=link_tipo, pause=pause,
                  list_delay=list_delay, select_tool=select_tool)
        prev_tipo = link_tipo
        done += 1
    return done


def run_calibrate(data, router_name, topology_path, tipo, recalibrate_base=False):
    """
    Captura lo necesario para cablear con 'tipo'. El icono del rayo y la
    geometria de la lista (list_offset/list_row_height) son GENERICOS
    (no dependen del tipo de cable): si ya estan calibrados no se vuelven
    a pedir, salvo recalibrate_base=True. El icono de 'tipo' en
    cable_icons SIEMPRE se (re)captura, sin tocar los demas tipos ya
    guardados en ese diccionario.

    Usa un router/dispositivo YA colocado como referencia de posicion (su
    (x, y) sale del registro, no hace falta que el usuario lo mida).
    """
    topo = load_topology(topology_path)
    device = find_device(topo, router_name)
    dx, dy = device["posicion"]
    cable_icons = data.setdefault("cable_icons", {})

    print()
    print(f"  Referencia: {device['nombre']} ({device.get('modelo', '?')}) "
          f"en ({dx}, {dy})")
    print("-" * 64)

    if recalibrate_base or data.get("cable_icon") is None:
        print("  1) En Packet Tracer, clic en el icono de cable (rayo) en la paleta.")
        p = coords_io.capture_point("icono de cable (rayo)", data.get("cable_icon"))
        if p is not None:
            data["cable_icon"] = p
    else:
        print(f"  1) icono de cable (rayo) ya calibrado: {data['cable_icon']} "
              f"(usa --recalibrate para repetirlo)")

    print(f"  2) Elegi el tipo de cable '{tipo}' en la sub-paleta que aparecio.")
    p = coords_io.capture_point(f"icono de cable '{tipo}'", cable_icons.get(tipo))
    if p is not None:
        cable_icons[tipo] = p

    if (recalibrate_base or data.get("list_offset") is None
            or data.get("list_row_height") is None):
        print(f"  3) Clic VOS A MANO en {device['nombre']} ({dx},{dy}) para que")
        print("     se despliegue su lista de interfaces (queda abierta en pantalla).")
        p0 = coords_io.capture_point("PRIMER item de la lista (indice 0)")
        p1 = coords_io.capture_point("SEGUNDO item de la lista (indice 1)")
        if p0 is not None and p1 is not None:
            data["list_offset"] = [p0[0] - dx, p0[1] - dy]
            data["list_row_height"] = p1[1] - p0[1]
            print(f"     -> list_offset = {data['list_offset']}, "
                  f"list_row_height = {data['list_row_height']}")
        elif p0 is not None or p1 is not None:
            print("     [!] Hacen falta AMBOS puntos (item 0 e item 1) para calcular "
                  "list_offset/list_row_height; no se guardo ninguno de los dos.")
    else:
        print(f"  3) geometria de lista ya calibrada: offset={data['list_offset']}, "
              f"row_height={data['list_row_height']} (usa --recalibrate para repetirla)")

    coords_io.save_coords(CABLE_COORDS_PATH, data)


def main():
    ap = argparse.ArgumentParser(
        description="Crea un cable entre dos dispositivos en Packet Tracer.")
    ap.add_argument("r1", nargs="?", help="Nombre del dispositivo 1 (ej. R01)")
    ap.add_argument("idx1", nargs="?", type=int,
                    help="Indice de interfaz en r1 (de build.compute_menu_index)")
    ap.add_argument("r2", nargs="?", help="Nombre del dispositivo 2 (ej. R04, Sw1)")
    ap.add_argument("idx2", nargs="?", type=int,
                    help="Indice de interfaz en r2 (de build.compute_menu_index)")
    ap.add_argument("--tipo", default=DEFAULT_TIPO,
                    help=f"Tipo de cable: clave en cable_coords.json -> cable_icons "
                         f"(ej. 'serial', 'copper'). Def. '{DEFAULT_TIPO}'.")
    ap.add_argument("--topology", default=TOPOLOGY_ACTUAL_PATH,
                    help="Registro de topologia (def. data/topology/topologia_actual.json).")
    ap.add_argument("--calibrate", action="store_true",
                    help="Calibrar cable_coords.json para --tipo y salir (requiere --router).")
    ap.add_argument("--router", help="Dispositivo de referencia para --calibrate (ej. R01).")
    ap.add_argument("--recalibrate", action="store_true",
                    help="Recapturar TAMBIEN lo generico (rayo + geometria de lista), "
                         "no solo el icono de --tipo.")
    tool_grp = ap.add_mutually_exclusive_group()
    tool_grp.add_argument("--select-tool", dest="select_tool", action="store_true",
                          default=None,
                          help="Reselecciona rayo+serial antes de cablear (def.: si).")
    tool_grp.add_argument("--no-select-tool", dest="select_tool", action="store_false",
                          help="Asume la herramienta YA armada de un cable anterior "
                               "del MISMO --tipo (para probar que Packet Tracer la "
                               "deja armada).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Imprime el plan sin mover el mouse.")
    ap.add_argument("--pause", type=float, default=0.4,
                    help="Pausa entre clics (def. 0.4).")
    ap.add_argument("--list-delay", type=float, default=0.4,
                    help="Espera tras clickear un dispositivo, a que abra su "
                         "lista de interfaces (def. 0.4).")
    ap.add_argument("--countdown", type=int, default=5,
                    help="Segundos de cuenta regresiva (def. 5).")
    args = ap.parse_args()

    print("=" * 64)
    print("  cable_link.py :: cablear entre dos dispositivos")
    print("=" * 64)
    print("  [!] EXPERIMENTAL: mecanica confirmada a mano; offsets a calibrar.")
    print(f"  DPI awareness: {dpi_aware.STATUS}")
    ok, msg = dpi_aware.verify()
    print(f"  {'' if ok else '[!] '}{msg}")
    print(f"  Coords : {CABLE_COORDS_PATH}")

    data = _migrate_old_schema(coords_io.load_coords(CABLE_COORDS_PATH))

    if args.calibrate:
        if not args.router:
            ap.error("--calibrate requiere --router (ej. --router R01).")
        run_calibrate(data, args.router, args.topology, args.tipo,
                     recalibrate_base=args.recalibrate)
        return

    if not (args.r1 and args.idx1 is not None and args.r2 and args.idx2 is not None):
        ap.error("Indica: R1 IDX1 R2 IDX2 (o usa --calibrate --tipo T --router NOMBRE).")

    select_tool = True if args.select_tool is None else args.select_tool

    topo = load_topology(args.topology)
    dev1 = find_device(topo, args.r1)
    dev2 = find_device(topo, args.r2)
    pos1, pos2 = tuple(dev1["posicion"]), tuple(dev2["posicion"])
    print(f"  Tipo de cable: '{args.tipo}'")
    print(f"  {dev1['nombre']} ({dev1.get('modelo', '?')}) en {pos1}  "
          f"-- interfaz #{args.idx1}")
    print(f"  {dev2['nombre']} ({dev2.get('modelo', '?')}) en {pos2}  "
          f"-- interfaz #{args.idx2}")
    print(f"  Reseleccionar herramienta (rayo+'{args.tipo}'): "
          f"{'SI' if select_tool else 'NO (asume armada de un cable anterior del mismo tipo)'}")

    if args.recalibrate:
        run_calibrate(data, args.router or args.r1, args.topology, args.tipo,
                     recalibrate_base=True)

    missing = missing_coords(data, args.tipo)
    if missing:
        print(f"  Faltan puntos calibrados: {', '.join(missing)}.")
        if not args.dry_run:
            print(f"  Calibra primero:  python cable_link.py --calibrate "
                  f"--tipo {args.tipo} --router {args.r1}")
            sys.exit(1)

    ix1, iy1 = interface_item_xy(pos1, args.idx1, data) if not missing else ("?", "?")
    ix2, iy2 = interface_item_xy(pos2, args.idx2, data) if not missing else ("?", "?")

    if args.dry_run:
        print("-" * 64)
        print("  Plan:")
        step = 1
        if select_tool:
            print(f"    {step}. clic icono de cable (rayo) "
                  f"{data.get('cable_icon', 'SIN CALIBRAR')}")
            step += 1
            print(f"    {step}. clic icono de cable '{args.tipo}' "
                  f"{data.get('cable_icons', {}).get(args.tipo, 'SIN CALIBRAR')}")
            step += 1
        print(f"    {step}. clic en {dev1['nombre']} {pos1}")
        step += 1
        print(f"    {step}. clic en item #{args.idx1} de su lista -> ({ix1}, {iy1})")
        step += 1
        print(f"    {step}. clic en {dev2['nombre']} {pos2}")
        step += 1
        print(f"    {step}. clic en item #{args.idx2} de su lista -> ({ix2}, {iy2})")
        print()
        print("  DRY-RUN: no se movera el mouse.")
        print("=" * 64)
        return

    print()
    print("  Pon el foco en Packet Tracer.")
    for i in range(max(0, args.countdown), 0, -1):
        sys.stdout.write(f"\r  Empezando en {i}...   ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r  Cableando...                 \n")
    sys.stdout.flush()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    done = False
    try:
        cable_link(pos1, args.idx1, pos2, args.idx2, data, tipo=args.tipo,
                  pause=args.pause, list_delay=args.list_delay,
                  select_tool=select_tool)
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
        print(f"  Cable creado (se espera): {dev1['nombre']} #{args.idx1} <-> "
              f"{dev2['nombre']} #{args.idx2}")
        print("  Revisa en Packet Tracer:")
        print("    - ¿Aparecio el cable entre los dos routers?")
        print("    - ¿Las interfaces conectadas son las correctas (no otras)?")
        print("    - Si algo cayo en el lugar equivocado, recalibra:")
        print(f"        python cable_link.py --calibrate --tipo {args.tipo} "
              f"--router {dev1['nombre']}")
    else:
        print("  Ejecucion abortada; nada garantizado.")
        sys.exit(1)
    print("=" * 64)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrumpido.")
