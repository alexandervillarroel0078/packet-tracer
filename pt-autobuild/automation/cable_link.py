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
(offset del item 0 + altura de fila). Se capturan en vivo con calibrate_cable() (pestana
Calibracion: mueve el mouse y pulsa F8), NO se miden en una imagen.

Reutiliza core/:
    dpi_aware    marca el proceso DPI-aware (antes que pyautogui)
    coords       capture_point / load_coords / save_coords
    ptwindow     click_point / park_mouse
    topology     load_topology / find_device (posicion de cada dispositivo)

Uso (desde el panel, o como funciones):
    calibrate_cable("serial", "R01", log=...)              # calibra el icono de ese tipo
    link_devices("R01", 3, "R04", 3, tipo="serial")        # dry-run por defecto
    link_devices("R01", 3, "R04", 3, tipo="serial", dry_run=False)

Los INDICES (3, 3 / 5, 3 arriba) son el resultado YA calculado por
core.topology.compute_menu_index() -- este script no los recalcula, solo hace los
clics. Fuera de la calibracion, asume que Packet Tracer no tiene NADA cableado todavia en
los dispositivos indicados (el indice de menu depende de las interfaces ya usadas). El
cableado automatico desde build_topology NO esta implementado todavia: solo se calcula el
plan; estas funciones se usan a mano.

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre pasos.
"""


from core import coords as coords_io
from core import paths, ptwindow
from core.errors import PTError
from core.topology import load_topology, find_device
from automation import common

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
    misma que build_topology uso para colocarlo), no la del item.
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
            raise PTError(
                f"falta calibrar el icono del tipo de cable '{tipo}' "
                f"(cable_coords.json -> cable_icons.{tipo}); calibralo en la pestana Calibracion.")
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
    duplica esta logica en build: se reutilizara cable_all() tal cual.

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


def calibrate_cable(tipo, router_name, *, recalibrate_base=False, topology_path=None,
                    countdown=3, log=None, cancel=None):
    """
    Captura (con F8, ESC cancela) lo necesario para cablear con 'tipo'. El icono del rayo y
    la geometria de la lista (list_offset/list_row_height) son GENERICOS (no dependen del
    tipo de cable): si ya estan calibrados no se vuelven a pedir, salvo
    recalibrate_base=True. El icono de 'tipo' en cable_icons SIEMPRE se (re)captura, sin
    tocar los demas tipos ya guardados.

    Usa un router/dispositivo YA colocado como referencia (su (x, y) sale del registro).
    Devuelve el dict guardado. Lanza PTError / CancelledError.
    """
    log = common.get_log(log)
    topology_path = topology_path or paths.TOPOLOGY_ACTUAL_PATH
    path = paths.CABLE_COORDS_PATH
    data = _migrate_old_schema(coords_io.load_coords(path))
    topo = load_topology(topology_path)
    device = find_device(topo, router_name)
    dx, dy = device["posicion"]
    cable_icons = data.setdefault("cable_icons", {})

    def grab(label, previous=None):
        common.check_cancel(cancel)
        p = coords_io.capture_point(label, previous, countdown=countdown, cancel=cancel)
        common.check_cancel(cancel)
        return p

    log(f"  Referencia: {device['nombre']} ({device.get('modelo', '?')}) en ({dx}, {dy})")
    log("-" * 64)

    if recalibrate_base or data.get("cable_icon") is None:
        log("  1) En Packet Tracer, clic en el icono de cable (rayo) en la paleta.")
        p = grab("icono de cable (rayo)", data.get("cable_icon"))
        if p is not None:
            data["cable_icon"] = p
    else:
        log(f"  1) icono de cable (rayo) ya calibrado: {data['cable_icon']} "
            "(marca 'recalibrar base' para repetirlo)")

    log(f"  2) Elige el tipo de cable '{tipo}' en la sub-paleta que aparecio.")
    p = grab(f"icono de cable '{tipo}'", cable_icons.get(tipo))
    if p is not None:
        cable_icons[tipo] = p

    if (recalibrate_base or data.get("list_offset") is None
            or data.get("list_row_height") is None):
        log(f"  3) Haz clic A MANO en {device['nombre']} ({dx},{dy}) para que")
        log("     se despliegue su lista de interfaces (queda abierta en pantalla).")
        p0 = grab("PRIMER item de la lista (indice 0)")
        p1 = grab("SEGUNDO item de la lista (indice 1)")
        if p0 is not None and p1 is not None:
            data["list_offset"] = [p0[0] - dx, p0[1] - dy]
            data["list_row_height"] = p1[1] - p0[1]
            log(f"     -> list_offset = {data['list_offset']}, "
                f"list_row_height = {data['list_row_height']}")
        elif p0 is not None or p1 is not None:
            log("     [!] Hacen falta AMBOS puntos (item 0 e item 1) para calcular "
                "list_offset/list_row_height; no se guardo ninguno de los dos.")
    else:
        log(f"  3) geometria de lista ya calibrada: offset={data['list_offset']}, "
            f"row_height={data['list_row_height']} (marca 'recalibrar base' para repetirla)")

    if not coords_io.save_coords(path, data):
        raise PTError(f"no se pudo guardar {path}")
    return data


def link_devices(r1, idx1, r2, idx2, *, tipo=DEFAULT_TIPO, select_tool=True, dry_run=True,
                 topology_path=None, pause=0.4, list_delay=0.4, countdown=5,
                 log=None, cancel=None):
    """
    Crea UN cable entre dos dispositivos ya colocados (por nombre en el registro de
    topologia). idx1/idx2: indices YA calculados de la interfaz en cada dispositivo.
    dry_run=True (por defecto) solo muestra el plan. EXPERIMENTAL.
    Lanza PTError (faltan puntos calibrados, dispositivo desconocido) o CancelledError.
    """
    log = common.get_log(log)
    topology_path = topology_path or paths.TOPOLOGY_ACTUAL_PATH
    log("=" * 64)
    log("  Cablear entre dos dispositivos")
    log("=" * 64)
    log("  [!] EXPERIMENTAL: mecanica confirmada a mano; offsets a calibrar.")
    common.dpi_header(log)
    log(f"  Coords : {paths.CABLE_COORDS_PATH}")

    data = _migrate_old_schema(coords_io.load_coords(paths.CABLE_COORDS_PATH))
    topo = load_topology(topology_path)
    dev1 = find_device(topo, r1)
    dev2 = find_device(topo, r2)
    pos1, pos2 = tuple(dev1["posicion"]), tuple(dev2["posicion"])
    log(f"  Tipo de cable: '{tipo}'")
    log(f"  {dev1['nombre']} ({dev1.get('modelo', '?')}) en {pos1}  -- interfaz #{idx1}")
    log(f"  {dev2['nombre']} ({dev2.get('modelo', '?')}) en {pos2}  -- interfaz #{idx2}")
    log(f"  Reseleccionar herramienta (rayo+'{tipo}'): "
        f"{'SI' if select_tool else 'NO (asume armada de un cable anterior del mismo tipo)'}")

    missing = missing_coords(data, tipo)
    if missing:
        log(f"  Faltan puntos calibrados: {', '.join(missing)}.")
        if not dry_run:
            raise PTError("faltan puntos calibrados de cables: " + ", ".join(missing)
                          + ". Calibralos en la pestana Calibracion.")

    ix1, iy1 = interface_item_xy(pos1, idx1, data) if not missing else ("?", "?")
    ix2, iy2 = interface_item_xy(pos2, idx2, data) if not missing else ("?", "?")

    if dry_run:
        log("-" * 64)
        log("  Plan:")
        step = 1
        if select_tool:
            log(f"    {step}. clic icono de cable (rayo) {data.get('cable_icon', 'SIN CALIBRAR')}")
            step += 1
            log(f"    {step}. clic icono de cable '{tipo}' "
                f"{data.get('cable_icons', {}).get(tipo, 'SIN CALIBRAR')}")
            step += 1
        log(f"    {step}. clic en {dev1['nombre']} {pos1}")
        step += 1
        log(f"    {step}. clic en item #{idx1} de su lista -> ({ix1}, {iy1})")
        step += 1
        log(f"    {step}. clic en {dev2['nombre']} {pos2}")
        step += 1
        log(f"    {step}. clic en item #{idx2} de su lista -> ({ix2}, {iy2})")
        log("")
        log("  DRY-RUN: no se movera el mouse.")
        return False

    common.pyautogui_ready()
    common.countdown(countdown, log, cancel)

    def go():
        cable_link(pos1, idx1, pos2, idx2, data, tipo=tipo, pause=pause,
                   list_delay=list_delay, select_tool=select_tool)
        ptwindow.park_mouse()

    common.run_guarded(go)
    log(f"  Cable creado (se espera): {dev1['nombre']} #{idx1} <-> {dev2['nombre']} #{idx2}")
    return True
