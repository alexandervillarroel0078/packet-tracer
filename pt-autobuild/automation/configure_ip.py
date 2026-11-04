"""
configure_ip.py - Flujo COMPLETO de configuracion IP de un dispositivo.

    doble clic en el dispositivo -> Desktop -> IP Configuration -> Static
    -> escribir IPv4 / Mascara / Gateway -> cerrar la ventana

Con skip_open=True asume que la ventana YA esta abierta y en 'Desktop > IP
Configuration' (modo depuracion): solo escribe los 3 campos y no cierra.

La posicion del dispositivo NO se pasa a mano: se lee de topologia_actual.json
(el registro que genera build_topology) buscando el dispositivo por su nombre.

Puntos a calibrar (posicion fija en pantalla; la ventana emergente de Packet
Tracer abre siempre en el mismo sitio mientras no la muevas ni cambies la
resolucion). Todos en data/ip_config_coords.json:

    desktop_tab           pestana "Desktop" dentro de la ventana
    ip_configuration_item icono "IP Configuration" ("skip" si aparece directo)
    static_radio          radio button "Static"
    close_button          boton X de la ventana (lo reutiliza configure_router)
    ipv4_address / subnet_mask / default_gateway   campos de texto

Uso (desde el panel, pestana Configurar; o como funciones):
    configure_device_ip("PC0", "192.168.10.10", "255.255.255.0", "192.168.10.1")  # dry-run
    configure_device_ip("PC0", ..., dry_run=False)
    configure_device_ip("PC0", ..., dry_run=False, skip_open=True)  # ventana ya abierta
    calibrate_ip_window()                                          # captura con F8

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre clics.
"""


from core import coords as coords_io
from core import paths, ptwindow, validate
from core.errors import PTError
from core.topology import load_topology, find_device
from automation import common

SKIP = "skip"

# campos de texto, en el orden en que se escriben
FIELDS = [
    ("ipv4_address", "IPv4 Address"),
    ("subnet_mask", "Subnet Mask"),
    ("default_gateway", "Default Gateway"),
]

# puntos de navegacion de la ventana, en orden de calibracion
WINDOW_POINTS = [
    ("desktop_tab", "pestana 'Desktop'"),
    ("ip_configuration_item", "icono 'IP Configuration' (ESC si aparece directo)"),
    ("static_radio", "radio button 'Static'"),
    ("close_button", "boton X de la ventana"),
]

FIELD_POINTS = [
    ("ipv4_address", "campo 'IPv4 Address'"),
    ("subnet_mask", "campo 'Subnet Mask'"),
    ("default_gateway", "campo 'Default Gateway'"),
]

# claves de data/ip_config_coords.json que este flujo necesita calibradas
# ('ip_configuration_item' puede valer SKIP; basta con que no sea None).
REQUIRED_COORDS = ("desktop_tab", "ip_configuration_item", "static_radio",
                   "close_button", "ipv4_address", "subnet_mask", "default_gateway")


def apply_ip(data, dx, dy, ip, mask, gateway, *, pause=0.4, open_delay=0.5,
             tab_delay=0.4, skip_open=False):
    """Flujo completo de IP Configuration sobre el dispositivo en (dx, dy).

    Unica fuente de la secuencia: abrir ventana (doble clic) -> Desktop ->
    IP Configuration -> Static -> escribir IPv4/Mascara/Gateway -> cerrar.

    'data' es el dict de ip_config_coords.json YA cargado y validado por el
    llamador (usa REQUIRED_COORDS). No hace cuenta regresiva; asume que el
    llamador gestiona foco y pyautogui.FAILSAFE. Propaga FailSafeException /
    KeyboardInterrupt. Con skip_open=True solo escribe los 3 campos.
    """
    values = {"ipv4_address": ip, "subnet_mask": mask, "default_gateway": gateway}
    if not skip_open:
        ptwindow.open_device_window(dx, dy, open_delay)
        ptwindow.click_point(data["desktop_tab"], tab_delay)
        if data.get("ip_configuration_item") not in (None, SKIP):
            ptwindow.click_point(data["ip_configuration_item"], tab_delay)
        ptwindow.click_point(data["static_radio"], pause)
    for key, _ in FIELDS:
        ptwindow.type_into(data[key], values[key], pause)
    if not skip_open:
        ptwindow.close_window(data["close_button"], pause)
    ptwindow.park_mouse()


def calibrate_ip_window(points=None, *, only_missing=False, countdown=3, log=None,
                        cancel=None):
    """
    Captura (F8; ESC cancela el punto) los puntos de la ventana IP y los guarda en
    data/ip_config_coords.json. En 'ip_configuration_item', ESC lo guarda como 'skip'
    (aparece directo al pulsar Desktop). Devuelve True si quedaron todos los puntos.

    Antes: doble clic en un PC (ventana abierta, sin moverla), Desktop > IP Configuration
    (Static) a mano. points = lista de (clave, etiqueta); por defecto todos.
    """
    log = common.get_log(log)
    points = points or (WINDOW_POINTS + FIELD_POINTS)
    path = paths.IP_CONFIG_COORDS_PATH
    data = coords_io.load_coords(path)
    log("  CALIBRACION de data/ip_config_coords.json")
    log("  1) En Packet Tracer, DOBLE CLIC en un PC para abrir su ventana. NO la muevas.")
    log("  2) Marca 'Desktop' y el boton X (visibles ya).")
    log("  3) Entra a Desktop > IP Configuration (modo Static) a mano.")
    log("     Para 'IP Configuration': si aparece directo al pulsar Desktop, pulsa ESC.")
    log("  4) Marca 'Static' y los 3 campos de texto.")
    log("-" * 64)
    changed = False
    for key, label in points:
        common.check_cancel(cancel)
        if only_missing and data.get(key) is not None:
            log(f"  {key:<22} ya calibrado: {data[key]}")
            continue
        p = coords_io.capture_point(label, data.get(key), countdown=countdown, cancel=cancel)
        common.check_cancel(cancel)
        if p is None:
            if key == "ip_configuration_item":
                data[key] = SKIP
                changed = True
                log(f"    -> '{key}' guardado como '{SKIP}' (no se hara clic)")
            continue
        data[key] = p
        changed = True
    if changed and not coords_io.save_coords(path, data):
        raise PTError(f"no se pudo guardar {path}")
    done = all(data.get(k) is not None for k, _ in WINDOW_POINTS + FIELD_POINTS)
    log("  Calibracion completa." if done else "  Faltan puntos por capturar.")
    return done


def configure_device_ip(name, ip, mask, gateway, *, skip_open=False, dry_run=True,
                        topology_path=None, pause=0.4, open_delay=0.5, tab_delay=0.4,
                        countdown=5, log=None, cancel=None):
    """
    Flujo completo de IP Configuration de un dispositivo del registro de topologia.
    dry_run=True (por defecto) solo muestra el plan. skip_open=True asume la ventana ya
    abierta en IP Configuration: solo escribe los 3 campos.
    Lanza PTError (datos invalidos, dispositivo desconocido, faltan puntos calibrados) o
    CancelledError (cancelado / failsafe).
    """
    log = common.get_log(log)
    topology_path = topology_path or paths.TOPOLOGY_ACTUAL_PATH
    log("=" * 64)
    log("  Configurar IP: abrir ventana + escribir IP")
    log("=" * 64)
    common.dpi_header(log)
    log(f"  Coords : {paths.IP_CONFIG_COORDS_PATH}")

    if not (name and ip and mask and gateway):
        raise PTError("indica: nombre, IP, mascara y gateway.")
    for label, val in (("IP", ip), ("mascara", mask), ("gateway", gateway)):
        if not validate.valid_ipish(val):
            raise PTError(f"{label} '{val}' no parece un IPv4 valido (x.x.x.x, 0-255).")

    data = coords_io.load_coords(paths.IP_CONFIG_COORDS_PATH)
    topology = load_topology(topology_path)
    device = find_device(topology, name)
    dx, dy = device["posicion"]
    log(f"  Dispositivo: {device['nombre']} ({device['tipo']} {device['modelo']}) "
        f"en ({dx}, {dy})")
    if device["tipo"] in ("router", "switch"):
        log("  [!] Aviso: routers y switches no tienen pestana 'Desktop'. Este flujo")
        log("      esta pensado para PC / Laptop / Server.")

    values = {"ipv4_address": ip, "subnet_mask": mask, "default_gateway": gateway}
    if skip_open:
        needed = [k for k, _ in FIELDS]
        plan_steps = [f"escribir {lbl} {data.get(k, 'SIN CALIBRAR')} <- '{values[k]}'"
                      for k, lbl in FIELDS]
    else:
        needed = [k for k, _ in WINDOW_POINTS] + [k for k, _ in FIELDS]
        plan_steps = [
            f"doble clic en ({dx}, {dy}); esperar {open_delay}s",
            f"clic 'Desktop' {data.get('desktop_tab', 'SIN CALIBRAR')}",
        ]
        ipc = data.get("ip_configuration_item", "SIN CALIBRAR")
        plan_steps.append(f"clic 'IP Configuration' {ipc}"
                          + ("  (se salta)" if ipc == SKIP else ""))
        plan_steps.append(f"clic 'Static' {data.get('static_radio', 'SIN CALIBRAR')}")
        plan_steps += [f"escribir {lbl} {data.get(k, 'SIN CALIBRAR')} <- '{values[k]}'"
                       for k, lbl in FIELDS]
        plan_steps.append(f"clic X (cerrar) {data.get('close_button', 'SIN CALIBRAR')}")

    if dry_run:
        log("")
        log("  Plan:" + ("  [skip_open]" if skip_open else ""))
        for i, step in enumerate(plan_steps, 1):
            log(f"    {i}. {step}")
        log("")
        log("  DRY-RUN: no se movera el mouse.")
        return False

    missing = [k for k in needed if data.get(k) is None]
    if missing:
        raise PTError("faltan puntos calibrados de la ventana IP: " + ", ".join(missing)
                      + ". Calibralos en la pestana Calibracion.")

    log("  Plan: la ventana debe estar YA en Desktop > IP Configuration." if skip_open else
        "  Plan: doble clic -> Desktop -> IP Configuration -> Static -> 3 campos -> cerrar")
    common.pyautogui_ready()
    common.countdown(countdown, log, cancel)

    def go():
        apply_ip(data, dx, dy, ip, mask, gateway, pause=pause, open_delay=open_delay,
                 tab_delay=tab_delay, skip_open=skip_open)

    common.run_guarded(go)
    log(f"  {device['nombre']}: IPv4 {ip} / {mask} / GW {gateway}")
    return True
