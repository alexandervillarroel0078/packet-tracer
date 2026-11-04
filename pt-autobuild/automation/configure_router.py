"""
configure_router.py - Flujo basico de configuracion de un router por CLI.

    doble clic en el router -> pestana CLI -> (foco consola) -> comandos IOS
    para cambiar el hostname -> cerrar la ventana

Alcance limitado a proposito: SOLO cambia el hostname. No hace
'copy running-config startup-config' ni 'write memory'.

Reutiliza:
    core/                       dpi_aware, coords, ptwindow, validate, topology
    data/topology/topologia_actual.json   posicion (x,y) del router por su nombre
    data/ip_config_coords.json  close_button  (misma ventana, mismo pixel; no se
                                duplica aqui para evitar desincronizacion)

Coordenadas propias de este flujo (data/router_coords.json):
    cli_tab      pestana "CLI" dentro de la ventana del dispositivo   (obligatorio)
    cli_console  punto dentro del area de texto de la consola          (opcional;
                 "skip" si al abrir CLI el foco ya cae solo en la consola)

Uso (desde el panel, pestana Configurar; o como funciones):
    set_router_hostname("Router0", "R01")                  # dry-run por defecto
    set_router_hostname("Router0", "R01", dry_run=False)
    calibrate_router()                                     # captura con F8

Seguridad: cuenta regresiva, failsafe de pyautogui (mouse a la esquina
superior izquierda = aborta), pausa configurable entre clics/comandos.
"""

import time

from core import coords as coords_io  # noqa: E402
from core import paths, ptwindow, validate  # noqa: E402
from core.errors import PTError
from core.topology import load_topology, find_device  # noqa: E402

import pyautogui  # noqa: E402

from automation import common

SKIP = "skip"

# puntos propios, en orden de calibracion
ROUTER_POINTS = [
    ("cli_tab", "pestana 'CLI'"),
    ("cli_console", "area de consola (ESC si el foco ya cae solo)"),
]


def get_close_button():
    """close_button vive en data/ip_config_coords.json (fuente unica)."""
    return coords_io.load_coords(paths.IP_CONFIG_COORDS_PATH).get("close_button")


def calibrate_router(*, only_missing=False, countdown=3, log=None, cancel=None):
    """
    Captura (F8; ESC cancela el punto) los puntos propios del router y los guarda en
    data/router_coords.json. En 'cli_console', ESC lo guarda como 'skip'.
    Devuelve True si 'cli_tab' quedo calibrado.
    """
    log = common.get_log(log)
    path = paths.ROUTER_COORDS_PATH
    data = coords_io.load_coords(path)
    log("  CALIBRACION de data/router_coords.json")
    log("  En Packet Tracer, haz DOBLE CLIC en un router para abrir su ventana.")
    log("  NO la muevas. Marca la pestana 'CLI'. Para 'cli_console': entra a CLI")
    log("  y, si el foco ya esta en la consola, pulsa ESC para guardarlo como 'skip'.")
    log("-" * 64)
    changed = False
    for key, label in ROUTER_POINTS:
        common.check_cancel(cancel)
        if only_missing and data.get(key) is not None:
            log(f"  {key:<12} ya calibrado: {data[key]}")
            continue
        p = coords_io.capture_point(label, data.get(key), countdown=countdown, cancel=cancel)
        common.check_cancel(cancel)
        if p is None:
            if key == "cli_console":
                data[key] = SKIP
                changed = True
                log(f"    -> '{key}' guardado como '{SKIP}' (no se hara clic)")
            continue
        data[key] = p
        changed = True
    if changed and not coords_io.save_coords(path, data):
        raise PTError(f"no se pudo guardar {path}")
    done = data.get("cli_tab") is not None
    log("  Calibracion completa." if done else "  Falta 'cli_tab' por capturar.")
    return done


def run_cli_sequence(hostname, cmd_pause):
    """[Enter] -> enable -> configure terminal -> hostname X -> end."""
    pyautogui.press("enter")
    time.sleep(cmd_pause)
    for cmd in ("enable", "configure terminal", f"hostname {hostname}", "end"):
        pyautogui.typewrite(cmd, interval=0.03)
        pyautogui.press("enter")
        time.sleep(cmd_pause)


def set_router_hostname(name, hostname, *, dry_run=True, topology_path=None, pause=0.4,
                        open_delay=0.5, tab_delay=0.4, cmd_pause=0.6, countdown=5,
                        log=None, cancel=None):
    """
    Cambia el hostname de un router del registro de topologia via CLI. dry_run=True (por
    defecto) solo muestra el plan. Lanza PTError (datos invalidos, no es router, faltan
    puntos calibrados) o CancelledError (cancelado / failsafe).
    """
    log = common.get_log(log)
    topology_path = topology_path or paths.TOPOLOGY_ACTUAL_PATH
    log("=" * 64)
    log("  Cambiar hostname de un router via CLI")
    log("=" * 64)
    common.dpi_header(log)
    log(f"  Coords router : {paths.ROUTER_COORDS_PATH}")
    log(f"  close_button  : {paths.IP_CONFIG_COORDS_PATH} (reutilizado)")

    if not (name and hostname):
        raise PTError("indica: nombre del router y hostname nuevo.")
    if not validate.valid_hostname(hostname):
        raise PTError(f"hostname '{hostname}' invalido: empieza por letra, solo "
                      f"letras/digitos/guiones, sin guion final, max 63.")

    data = coords_io.load_coords(paths.ROUTER_COORDS_PATH)
    topology = load_topology(topology_path)
    device = find_device(topology, name)
    if device["tipo"] != "router":
        raise PTError(f"'{device['nombre']}' es tipo '{device['tipo']}', no 'router'. "
                      f"Este flujo es solo para routers.")
    dx, dy = device["posicion"]
    close_btn = get_close_button()
    log(f"  Router: {device['nombre']} ({device['modelo']}) en ({dx}, {dy})")

    if dry_run:
        console = data.get("cli_console", "SIN CALIBRAR")
        log("")
        log("  Plan:")
        log(f"    1. doble clic en ({dx}, {dy})")
        log(f"    2. esperar {open_delay}s")
        log(f"    3. clic 'CLI'        {data.get('cli_tab', 'SIN CALIBRAR')}")
        log(f"    4. clic consola      {console}" + ("  (se salta)" if console == SKIP else ""))
        log(f"    5. secuencia CLI (pausa {cmd_pause}s entre lineas):")
        log("         [Enter]")
        for cmd in ("enable", "configure terminal", f"hostname {hostname}", "end"):
            log(f"         {cmd}  [Enter]")
        log(f"    6. clic X (cerrar)   {close_btn if close_btn else 'FALTA en ip_config_coords.json'}")
        log("")
        log("  DRY-RUN: no se movera el mouse.")
        return False

    if data.get("cli_tab") is None:
        raise PTError("falta calibrar 'cli_tab' (pestana CLI del router). "
                      "Calibralo en la pestana Calibracion.")
    if close_btn is None:
        raise PTError("no hay 'close_button' en data/ip_config_coords.json. "
                      "Calibra la ventana IP en la pestana Calibracion.")

    log("  Plan: doble clic router -> CLI -> comandos hostname -> cerrar")
    log("  La ventana del router se abrira sola.")
    common.pyautogui_ready()
    common.countdown(countdown, log, cancel)

    def go():
        ptwindow.open_device_window(dx, dy, open_delay)
        ptwindow.click_point(data["cli_tab"], tab_delay)
        if data.get("cli_console") not in (None, SKIP):
            ptwindow.click_point(data["cli_console"], pause)
        run_cli_sequence(hostname, cmd_pause)
        ptwindow.close_window(close_btn, pause)
        ptwindow.park_mouse()

    common.run_guarded(go)
    log(f"  {device['nombre']}: hostname -> {hostname}")
    log("  (No se guardo la config: falta 'copy run start', fuera de alcance.)")
    return True
