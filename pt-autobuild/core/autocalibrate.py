"""
core.autocalibrate - autocalibracion con IA (vision) para pt-autobuild.

Flujo (ver run_autocalibrate):
    1. Captura la ventana de Packet Tracer (pixeles fisicos; DPI aware).
    2. Cache: si resolucion / escala DPI / posicion de ventana no cambiaron y los
       recortes de referencia guardados siguen encontrandose en su sitio, NO se
       llama a la API.
    3. Envia la captura (redimensionada, base64) a la API de Anthropic pidiendo
       SOLO JSON con la posicion de cada elemento en pixeles de la imagen enviada.
    4. Convierte esas coordenadas a coordenadas reales de pantalla.
    5. Refinamiento: recorta una region alrededor de cada punto, la guarda en
       reference_images/ y la busca (cv2.matchTemplate) en una captura NUEVA. Si la
       confianza es baja reintenta (max. 2) pidiendo a la IA que afine sobre un
       recorte ampliado de esa zona; si sigue fallando -> "requiere manual".
    6. Guarda en data/coords.json (mismo formato de siempre) + una seccion
       "autocalibrate" con resolucion, escala DPI, ventana y estado por elemento.

Limite honesto de la verificacion: matchTemplate comprueba que la zona es
visualmente distintiva y estable (el punto cae sobre algo reconocible que se
vuelve a encontrar ahi), no que la IA haya elegido el elemento semanticamente
correcto. Por eso la salida marca la confianza y "Solo mostrar" (dry-run) permite revisar antes.

La logica pura (conversion de coordenadas, validacion del JSON de la IA, decision
de cache) no depende de pyautogui/cv2/red y esta cubierta por tests/.
"""

import base64
import io
import json
import os
import re
import sys
import tempfile
from typing import NamedTuple

from core import ai_providers, settings
from core.ai_providers import AIConfig
from core.errors import AutoCalibrateError
from core.log import emit
from core.paths import (CABLE_COORDS_PATH, COORDS_PATH, IP_CONFIG_COORDS_PATH,
                        REFERENCE_IMAGES_DIR)

META_KEY = "autocalibrate"
META_VERSION = 1

MAX_SEND_SIDE = 1568      # lado mayor maximo de la imagen enviada (px)
TEMPLATE_SIZE = 96        # lado del recorte de referencia (px de captura)
ZOOM_W, ZOOM_H = 480, 320  # region (unidades de pantalla) del reintento
MAX_RETRIES = 2
MIN_CONFIDENCE = 0.90
MATCH_TOLERANCE = 4       # px de captura permitidos entre lo esperado y lo hallado
MIN_TEMPLATE_STD = 6.0    # desviacion tipica minima (0-255): recorte "plano" = inutil
WINDOW_TOLERANCE = 2      # px de diferencia aceptados en la posicion de la ventana
DPI_TOLERANCE = 0.01
API_TIMEOUT = 90

# elemento -> (seccion, clave) en coords.json (mismo esquema de siempre)
ELEMENTS = {
    "search_field": ("search_field", None),
    "filtered_result": ("filtered_result", None),
    "canvas_top_left": ("canvas", "top_left"),
    "canvas_bottom_right": ("canvas", "bottom_right"),
}
# Sin estos tres no se puede construir; filtered_result es opcional porque solo
# existe en pantalla tras filtrar el buscador (si no se ve, queda para manual).
REQUIRED = ("search_field", "canvas_top_left", "canvas_bottom_right")

# En la pantalla del usuario, al filtrar con el buscador los resultados aparecen en la fila de
# iconos de dispositivos que queda JUSTO ENCIMA del campo de busqueda (ni a su derecha ni debajo).
FILTERED_RESULT_DESC = (
    "el PRIMER icono de la fila superior de resultados filtrados, justo ENCIMA del campo de "
    "busqueda (la fila de iconos de dispositivos que esta inmediatamente arriba del buscador, "
    "empezando por la izquierda). NO esta a la derecha ni debajo del buscador. Si esa fila "
    "no muestra ningun icono, devuelve null"
)
# Geometria (unidades de pantalla) respecto al CENTRO del buscador: el resultado debe estar
# ENCIMA (al menos MIN_ABOVE y como mucho MAX_ABOVE) y dentro del ancho del panel de
# dispositivos, que se aproxima por +-MAX_DX alrededor del centro del buscador.
FILTERED_MIN_ABOVE = 8
FILTERED_MAX_ABOVE = 220
FILTERED_MAX_DX = 220

DESCRIPTIONS = {
    "search_field": 'centro del campo de texto "Search for device" (buscador de '
                    "dispositivos, abajo a la izquierda, con la lupa)",
    "filtered_result": "centro de " + FILTERED_RESULT_DESC,
    "canvas_top_left": "esquina superior izquierda del area de trabajo (lienzo "
                       "blanco/cuadriculado donde se sueltan los dispositivos), "
                       "justo dentro del area, bajo la barra de herramientas superior",
    "canvas_bottom_right": "esquina inferior derecha del area de trabajo (lienzo), "
                           "justo dentro del area, encima de la paleta de "
                           "dispositivos y a la izquierda de la barra vertical derecha",
}


GROUPS = ("main", "cable", "ip")


def _file_paths():
    """Rutas de los JSON de coordenadas, leidas al momento (no congeladas al importar)."""
    return {"coords": COORDS_PATH, "cable": CABLE_COORDS_PATH, "ip": IP_CONFIG_COORDS_PATH}


GROUP_FILE = {"main": "coords", "cable": "cable", "ip": "ip"}

# Estados de UI que hacen visibles a los elementos (se le piden a la IA como booleanos)
STATES = {
    "main": "Packet Tracer en su vista principal (lienzo, paleta de dispositivos y barras)",
    "cable_palette": "la categoria de conexiones (rayo) esta seleccionada y la paleta "
                     "inferior muestra los iconos de TIPOS de cable",
    "interface_menu": "con un cable armado, se hizo clic en un dispositivo y esta desplegada "
                      "la lista de sus interfaces",
    "ip_window": "hay abierta la ventana de configuracion de un dispositivo "
                 "(pestanas arriba, boton X)",
    "ip_desktop": "esa ventana esta en la pestana Desktop mostrando los iconos de "
                  "aplicaciones (IP Configuration, Command Prompt...)",
    "ip_config": "esa ventana muestra el panel IP Configuration con el radio Static y los "
                 "campos IPv4 Address / Subnet Mask / Default Gateway",
}
STATE_HINTS = {
    "main": "Packet Tracer visible y sin ventanas encima",
    "cable_palette": "clic en la categoria de conexiones (rayo) de la paleta inferior",
    "interface_menu": "con el cable armado, clic en un dispositivo del lienzo y DEJA el "
                      "mouse quieto sobre el (la lista debe seguir desplegada)",
    "ip_window": "doble clic en un PC para abrir su ventana",
    "ip_desktop": "en esa ventana, pestana Desktop (iconos de aplicaciones)",
    "ip_config": "en esa ventana, Desktop > IP Configuration con Static marcado",
}
TEST_MODEL = "2911"       # modelo que se escribe en el buscador para filtrar
FILTER_WAIT = 1.0         # s de espera tras escribir
MENU_ROW_MIN, MENU_ROW_MAX = 8, 80
MENU_COL_TOL = 20
MENU_MAX_OFFSET = 600


# =====================================================================
# LOGICA PURA (testeada en tests/test_autocalibrate.py)
# =====================================================================
def image_to_screen(x, y, origin, units_per_px):
    """
    Convierte un punto de la imagen ENVIADA a coordenadas de pantalla.

    origin        (ox, oy): esquina sup-izq de la region capturada, en unidades de
                  pantalla (las de pyautogui).
    units_per_px  (ux, uy): unidades de pantalla que representa 1 px de la imagen
                  enviada. Incluye el redimensionado y la escala DPI:
                      ux = (ancho_recorte_px / ancho_enviado_px) / px_por_unidad
    """
    return (int(round(origin[0] + x * units_per_px[0])),
            int(round(origin[1] + y * units_per_px[1])))


def compute_units_per_px(crop_px_size, sent_size, px_per_unit):
    """units_per_px para image_to_screen. px_per_unit = captura_px / pantalla_unidades
    (1.0 con el proceso DPI aware; p. ej. 1.25 si no lo esta al 125 %)."""
    if min(crop_px_size + sent_size) <= 0 or px_per_unit <= 0:
        raise ValueError("tamanos y escala deben ser positivos")
    return (crop_px_size[0] / sent_size[0] / px_per_unit,
            crop_px_size[1] / sent_size[1] / px_per_unit)


def compute_send_size(width, height, max_side=MAX_SEND_SIDE):
    """Tamano de la imagen a enviar: reduce (nunca amplia) hasta max_side."""
    longest = max(width, height)
    if longest <= max_side:
        return int(width), int(height)
    s = max_side / longest
    return max(1, int(round(width * s))), max(1, int(round(height * s)))


def extract_json_text(text):
    """Saca el objeto JSON de la respuesta aunque venga con ```json ... ``` o texto."""
    if not isinstance(text, str):
        raise AutoCalibrateError("la respuesta de la IA no es texto")
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AutoCalibrateError("la respuesta de la IA no contiene un objeto JSON")
    return text[start:end + 1]


def evaluate_match(confidence, found, expected, min_conf=MIN_CONFIDENCE,
                   tolerance=MATCH_TOLERANCE):
    """True si la coincidencia es fiable y cae donde se esperaba."""
    if confidence is None or confidence != confidence:  # None o NaN
        return False
    return (confidence >= min_conf
            and abs(found[0] - expected[0]) <= tolerance
            and abs(found[1] - expected[1]) <= tolerance)


def _rect_close(a, b, tol):
    return (a is not None and b is not None and len(a) == len(b) == 4
            and all(abs(p - q) <= tol for p, q in zip(a, b)))


def _validate_points(raw, image_size, names, min_canvas=100):
    """Valida {nombre: {x,y}|[x,y]|null}. -> (puntos, avisos). Ver parse_ai_response."""
    w, h = image_size
    points, warns = {}, []
    normalized = 0
    for name in names:
        v = raw.get(name) if isinstance(raw, dict) else None
        if v is None:
            warns.append(f"{name}: la IA no lo encontro")
            continue
        if isinstance(v, dict):
            v = [v.get("x"), v.get("y")]
        if (not isinstance(v, (list, tuple)) or len(v) != 2 or
                not all(isinstance(n, (int, float)) and not isinstance(n, bool)
                        for n in v)):
            warns.append(f"{name}: formato invalido ({v!r})")
            continue
        x, y = float(v[0]), float(v[1])
        if 0 <= x <= 1 and 0 <= y <= 1:
            normalized += 1
            warns.append(f"{name}: ({x:g}, {y:g}) parece una coordenada NORMALIZADA (0-1); "
                         f"se esperaban pixeles de la imagen {w}x{h}: rechazada")
            continue
        if not (0 <= x < w and 0 <= y < h):
            warns.append(f"{name}: ({x:g}, {y:g}) fuera de la imagen {w}x{h}: rechazada")
            continue
        points[name] = (int(round(x)), int(round(y)))

    if normalized:
        warns.append(f"coordenadas normalizadas: el modelo devolvio {normalized} punto(s) en "
                     "escala 0-1 en vez de pixeles; no se guardaron. Prueba con otro modelo "
                     "con vision.")
    tl, br = points.get("canvas_top_left"), points.get("canvas_bottom_right")
    if tl and br and (br[0] - tl[0] < min_canvas or br[1] - tl[1] < min_canvas):
        warns.append(f"lienzo incoherente (esquinas {tl} / {br}): descartado")
        del points["canvas_top_left"], points["canvas_bottom_right"]
    return points, warns


def _load_json_object(text):
    try:
        raw = json.loads(extract_json_text(text))
    except json.JSONDecodeError as e:
        raise AutoCalibrateError(f"JSON de la IA invalido: {e}") from e
    if not isinstance(raw, dict):
        raise AutoCalibrateError("el JSON de la IA debe ser un objeto")
    return raw


def parse_ai_response(text, image_size, names=tuple(ELEMENTS), min_canvas=100):
    """
    Parsea y valida una respuesta plana de la IA.

    Formato esperado: {"search_field": {"x": 10, "y": 20}, "filtered_result": null, ...}
    (tambien acepta [x, y]). Devuelve (puntos, avisos):
        puntos  {nombre: (x, y)} solo de los elementos validos (en pixeles de la
                imagen enviada); null / ausente / fuera de imagen se omiten.
        avisos  lista de textos explicando lo descartado.
    Lanza AutoCalibrateError si no hay JSON valido o no es un objeto.
    """
    return _validate_points(_load_json_object(text), image_size, names, min_canvas)


def parse_multi_response(text, image_size, point_names, state_names):
    """
    Respuesta con estados de UI:
        {"states": {estado: bool}, "points": {nombre: {x,y}|null}}
    Devuelve (puntos, estados, avisos). Un estado ausente o no booleano cuenta como False.
    """
    raw = _load_json_object(text)
    states_raw = raw.get("states")
    states = {s: (isinstance(states_raw, dict) and states_raw.get(s) is True)
              for s in state_names}
    points, warns = _validate_points(raw.get("points"), image_size, point_names)
    return points, states, warns


def get_path(data, path):
    """data[path[0]][path[1]]... o None si falta algun nivel."""
    cur = data
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def set_path(data, path, value):
    cur = data
    for k in path[:-1]:
        cur = cur.setdefault(k, {})
    cur[path[-1]] = value


def derive_menu_geometry(item0, item1, mouse):
    """
    Geometria de la lista de interfaces (ver cable_link.interface_item_xy):
        list_offset     = item0 - posicion del clic en el dispositivo (el mouse)
        list_row_height = item1.y - item0.y
    Lanza ValueError si los datos no son plausibles.
    """
    row_h = int(item1[1] - item0[1])
    if not (MENU_ROW_MIN <= row_h <= MENU_ROW_MAX):
        raise ValueError(f"altura de fila implausible ({row_h}px) entre los items 0 y 1")
    if abs(item1[0] - item0[0]) > MENU_COL_TOL:
        raise ValueError("los items 0 y 1 no estan en la misma columna")
    off = [int(item0[0] - mouse[0]), int(item0[1] - mouse[1])]
    if abs(off[0]) > MENU_MAX_OFFSET or abs(off[1]) > MENU_MAX_OFFSET:
        raise ValueError(
            f"offset {off} implausible: deja el mouse quieto donde hiciste clic en el "
            "dispositivo mientras la lista esta desplegada")
    return off, row_h


def element_status(has_value, record):
    """
    Estado mostrado por elemento: "ok" | "manual" (requiere manual) | "unverified"
    (sin verificar). Sin valor guardado siempre "manual"; con valor pero sin registro
    de verificacion, "unverified".
    """
    if not has_value:
        return "manual"
    status = record.get("status") if isinstance(record, dict) else None
    if status == "ok":
        return "ok"
    if status == "manual":
        return "manual"
    return "unverified"


def check_status(matched, state):
    """Resultado de re-verificar un punto guardado (--check, sin API)."""
    if matched:
        return "ok"
    # un elemento de la pantalla principal que no coincide se movio; uno que depende de
    # una ventana/menu puede simplemente no estar abierto: no se puede afirmar nada.
    return "manual" if state == "main" else "unverified"


def missing_states(elements, detected):
    """{estado: [nombres]} de los estados que los elementos necesitan y la IA no vio."""
    out = {}
    for el in elements:
        if not detected.get(el.state, False):
            out.setdefault(el.state, []).append(el.name)
    return out


def parse_groups(text):
    """'main,cable' -> ('main','cable'); 'all' o vacio -> todos. Valida los nombres."""
    if not text or text.strip().lower() == "all":
        return GROUPS
    groups = tuple(g.strip().lower() for g in text.split(",") if g.strip())
    unknown = [g for g in groups if g not in GROUPS]
    if unknown:
        raise AutoCalibrateError(
            f"grupo(s) desconocido(s): {', '.join(unknown)}. Validos: {', '.join(GROUPS)}, all")
    return groups


class Element(NamedTuple):
    name: str          # clave unica (= clave del JSON; "a.b" si esta anidada)
    file: str          # "coords" | "cable" | "ip"
    path: tuple        # ruta dentro del JSON
    group: str         # main | cable | ip
    state: str         # estado de UI necesario para verlo (ver STATES)
    desc: str
    ai_name: str = ""  # nombre pedido a la IA (por defecto = name)
    required: bool = True   # debe estar verificado "ok" para que valga la cache
    soft: bool = False      # vale la cache con que tenga valor o recorte guardado

    @property
    def ask(self):
        return self.ai_name or self.name

    @property
    def fname(self):
        return "auto_" + self.name.replace(".", "_") + ".png"


CABLE_TYPE_DESC = {
    "serial": 'el cable "Serial DCE" (serie) de la sub-paleta de cables',
    "copper": 'el cable de cobre directo ("Copper Straight-Through") de la sub-paleta de cables',
}


def build_registry(cable_data=None):
    """
    Todos los elementos calibrables, por nombre. Los tipos de cable salen de
    CABLE_TYPE_DESC y de lo que ya haya en cable_coords.json -> cable_icons.
    """
    R = {}

    def add(*a, **k):
        e = Element(*a, **k)
        R[e.name] = e

    for n, (section, sub) in ELEMENTS.items():
        add(n, "coords", (section,) if sub is None else (section, sub), "main", "main",
            DESCRIPTIONS[n], required=(n != "filtered_result"), soft=(n == "filtered_result"))

    add("cable_icon", "cable", ("cable_icon",), "cable", "main",
        "icono de la categoria de conexiones/cables (rayo) en la paleta inferior izquierda "
        "de categorias de dispositivos")
    types = list(CABLE_TYPE_DESC)
    types += [t for t in ((cable_data or {}).get("cable_icons") or {}) if t not in types]
    for t in types:
        add(f"cable_icons.{t}", "cable", ("cable_icons", t), "cable", "cable_palette",
            "centro del icono de " + CABLE_TYPE_DESC.get(t, f'cable tipo "{t}" de la sub-paleta'),
            required=False, soft=True)
    add("list_offset", "cable", ("list_offset",), "cable", "interface_menu",
        "centro del PRIMER item (indice 0) de la lista desplegable de interfaces",
        ai_name="menu_item_0", required=False, soft=True)
    add("list_row_height", "cable", ("list_row_height",), "cable", "interface_menu",
        "centro del SEGUNDO item (indice 1) de la misma lista de interfaces",
        ai_name="menu_item_1", required=False, soft=True)

    win = "ventana de configuracion de un dispositivo abierta"
    add("desktop_tab", "ip", ("desktop_tab",), "ip", "ip_window",
        f'centro de la pestana "Desktop" ({win})', required=False, soft=True)
    add("close_button", "ip", ("close_button",), "ip", "ip_window",
        f"centro del boton X que cierra la ventana ({win})", required=False, soft=True)
    add("ip_configuration_item", "ip", ("ip_configuration_item",), "ip", "ip_desktop",
        'centro del icono "IP Configuration" dentro de Desktop', required=False, soft=True)
    add("static_radio", "ip", ("static_radio",), "ip", "ip_config",
        'centro del radio button "Static"', required=False, soft=True)
    add("ipv4_address", "ip", ("ipv4_address",), "ip", "ip_config",
        'centro del campo de texto "IPv4 Address"', required=False, soft=True)
    add("subnet_mask", "ip", ("subnet_mask",), "ip", "ip_config",
        'centro del campo de texto "Subnet Mask"', required=False, soft=True)
    add("default_gateway", "ip", ("default_gateway",), "ip", "ip_config",
        'centro del campo de texto "Default Gateway"', required=False, soft=True)
    return R


def select_elements(registry, groups):
    """Elementos del registro cuyo grupo esta en `groups` (orden del registro)."""
    return [e for e in registry.values() if e.group in groups]


def cache_decision(meta, env, required=REQUIRED, soft=(), have=()):
    """
    Decide si la calibracion guardada puede reutilizarse SIN llamar a la API
    (antes de comprobar visualmente los recortes). Devuelve (ok, motivo).

    meta      seccion "autocalibrate" guardada (o None)
    env       {"resolution": [w,h], "dpi_scale": float, "window": [l,t,w,h]} y, si se
              indican, "provider" y "model" de IA: al cambiarlos hay que recalibrar
    required  elementos que deben estar verificados ("ok") con recorte
    soft      elementos que dependen de un menu/ventana: basta con que tengan valor
              (nombres en `have`) o un recorte guardado; no obligan a llamar a la API
    """
    if not isinstance(meta, dict) or meta.get("version") != META_VERSION:
        return False, "no hay autocalibracion previa"
    if "provider" in env and (meta.get("provider"), meta.get("model")) != (
            env["provider"], env.get("model")):
        return False, (f"cambio el proveedor/modelo de IA ({meta.get('provider')}/"
                       f"{meta.get('model')} -> {env['provider']}/{env.get('model')})")
    if list(meta.get("resolution") or []) != list(env["resolution"]):
        return False, f"cambio la resolucion ({meta.get('resolution')} -> {env['resolution']})"
    old_dpi = meta.get("dpi_scale")
    if not isinstance(old_dpi, (int, float)) or abs(old_dpi - env["dpi_scale"]) > DPI_TOLERANCE:
        return False, f"cambio la escala DPI ({old_dpi} -> {env['dpi_scale']})"
    if not _rect_close(meta.get("window"), env["window"], WINDOW_TOLERANCE):
        return False, f"cambio la ventana ({meta.get('window')} -> {env['window']})"
    elements = meta.get("elements") or {}
    for name in required:
        el = elements.get(name)
        if not isinstance(el, dict) or el.get("status") != "ok":
            return False, f"'{name}' no esta verificado en la calibracion previa"
        if not el.get("template") or not el.get("point"):
            return False, f"'{name}' sin recorte de referencia"
    for name in soft:
        el = elements.get(name)
        if name not in have and not (isinstance(el, dict) and el.get("template")):
            return False, f"'{name}' aun no esta calibrado"
    return True, "resolucion, escala y ventana sin cambios"


# =====================================================================
# ENTORNO: .env, captura, ventana, DPI
# =====================================================================
def load_config():
    """
    Proveedor activo (AI_PROVIDER), su clave y su modelo, desde .env / entorno.
    -> AIConfig(provider, key, model). Nunca se imprime la key.
    """
    cfg = settings.read_settings()
    provider = cfg["provider"]
    kv, mv = ai_providers.KEY_VARS[provider], ai_providers.MODEL_VARS[provider]
    if not cfg["api_key"]:
        raise AutoCalibrateError(
            f"falta {kv} ({ai_providers.label(provider)}). Configurala en la pestana Ajustes "
            f"(o en .env). Puedes obtenerla en {ai_providers.KEY_URLS[provider]}")
    if not cfg["model"]:
        raise AutoCalibrateError(
            f"falta {mv}: indica un modelo con vision de {ai_providers.label(provider)} en la "
            "pestana Ajustes (o en .env).")
    return AIConfig(provider, cfg["api_key"], cfg["model"])


def current_ai():
    """(proveedor, modelo) activos, SIN exigir la clave (para la clave de cache)."""
    cfg = settings.read_settings()
    return cfg["provider"], cfg["model"]


def redact(text, *keys):
    """Quita de `text` las claves dadas y todo lo que parezca una clave (OpenAI o Anthropic)."""
    return ai_providers.redact(text, *keys)


def get_dpi_scale():
    """Escala de Windows (1.0 = 100 %, 1.25 = 125 %...). 1.0 fuera de Windows."""
    if sys.platform != "win32":
        return 1.0
    try:
        import ctypes
        return round(ctypes.windll.user32.GetDpiForSystem() / 96.0, 3)
    except (AttributeError, OSError):
        return 1.0


def capture():
    """Captura de pantalla completa. Devuelve (PIL.Image, px_por_unidad)."""
    from core import dpi_aware  # noqa: F401  fija la DPI awareness; debe importarse antes de pyautogui
    import pyautogui
    shot = pyautogui.screenshot()
    return shot, shot.width / float(pyautogui.size()[0])


def find_pt_window(screen_size):
    """
    Rectangulo [left, top, w, h] (unidades de pantalla, recortado a la pantalla) de
    la ventana de Packet Tracer. Devuelve (rect, aviso|None); si no la encuentra
    usa la pantalla completa.
    """
    sw, sh = screen_size
    full = [0, 0, int(sw), int(sh)]
    try:
        from core import dpi_aware  # noqa: F401  fija la DPI awareness; debe importarse antes de pyautogui
        import pyautogui
        wins = [w for w in pyautogui.getWindowsWithTitle("Packet Tracer")
                if w.width > 0 and w.height > 0 and not getattr(w, "isMinimized", False)]
    except Exception:  # noqa: BLE001 - pygetwindow ausente / no Windows
        wins = []
    if not wins:
        return full, "no se encontro la ventana de Packet Tracer: se usa toda la pantalla"
    w = max(wins, key=lambda x: x.width * x.height)
    l, t = max(0, int(w.left)), max(0, int(w.top))
    r, b = min(int(sw), int(w.left + w.width)), min(int(sh), int(w.top + w.height))
    if r - l < 200 or b - t < 200:
        return full, "ventana de Packet Tracer demasiado pequena: se usa toda la pantalla"
    return [l, t, r - l, b - t], None


def current_env():
    from core import dpi_aware  # noqa: F401  fija la DPI awareness; debe importarse antes de pyautogui
    import pyautogui
    screen = [int(v) for v in pyautogui.size()]
    window, warn = find_pt_window(screen)
    return {"resolution": screen, "dpi_scale": get_dpi_scale(), "window": window}, warn


def crop_units(shot, px_per_unit, rect):
    """Recorta rect=[l,t,w,h] (unidades de pantalla) de la captura -> (imagen, tamano_px)."""
    box = [int(round(rect[0] * px_per_unit)), int(round(rect[1] * px_per_unit)),
           int(round((rect[0] + rect[2]) * px_per_unit)),
           int(round((rect[1] + rect[3]) * px_per_unit))]
    box[2], box[3] = min(box[2], shot.width), min(box[3], shot.height)
    img = shot.crop(tuple(box))
    return img, img.size


def png_b64(img, size):
    from PIL import Image
    if img.size != tuple(size):
        img = img.resize(tuple(size), Image.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# =====================================================================
# API de Anthropic
# =====================================================================
def call_vision_api(cfg, img_b64, prompt):
    """Peticion con imagen al proveedor de `cfg`. Devuelve el texto (el JSON pedido)."""
    return ai_providers.send(cfg, prompt, image_b64=img_b64, max_tokens=1024)


def test_connection(key, model, provider=None):
    """
    Comprueba clave, modelo y red del proveedor (def.: el activo) con una peticion minima
    de solo texto. Devuelve un mensaje de exito; lanza AutoCalibrateError con causa clara.
    """
    provider = ai_providers.normalize_provider(provider or settings.active_provider())
    name = ai_providers.label(provider)
    if not (key or "").strip():
        raise AutoCalibrateError(f"falta la API key de {name}.")
    model = (model or "").strip() or ai_providers.DEFAULT_MODELS[provider]
    if not model:
        raise AutoCalibrateError(
            f"falta el modelo de {name}: indica un modelo con vision.")
    cfg = AIConfig(provider, key.strip(), model)
    ai_providers.send(cfg, 'Responde unicamente con este objeto JSON: {"ok": true}',
                      max_tokens=16)
    return f"Conexion correcta con {name} (modelo {model})."


def build_prompt(names, image_size, descs=None):
    """Prompt plano: SOLO puntos. `descs` {nombre: descripcion} (def. DESCRIPTIONS)."""
    descs = descs or DESCRIPTIONS
    w, h = image_size
    lines = "\n".join(f'- "{n}": {descs[n]}' for n in names)
    example = ", ".join(f'"{n}": {{"x": 0, "y": 0}}' for n in names)
    return (
        "Esta es una captura de la interfaz de Cisco Packet Tracer. La imagen mide "
        f"{w}x{h} pixeles; el origen (0,0) es su esquina superior izquierda.\n"
        "Localiza estos elementos y devuelve su posicion en PIXELES DE ESTA IMAGEN:\n"
        f"{lines}\n\n"
        "Responde SOLO con un objeto JSON, sin texto ni markdown, con este formato "
        f"exacto: {{{example}}}\n"
        "Usa null para cualquier elemento que no estes seguro de ver."
    )


def build_multi_prompt(elements, image_size):
    """Prompt con estados de UI: la IA indica que estados ve y solo da puntos de esos."""
    w, h = image_size
    states = list(dict.fromkeys(e.state for e in elements))
    st_lines = "\n".join(f'- "{s}": {STATES[s]}' for s in states)
    el_lines = "\n".join(f'- "{e.ask}" (solo visible si "{e.state}" es true): {e.desc}'
                         for e in elements)
    ex_states = ", ".join(f'"{s}": true' for s in states)
    ex_points = ", ".join(f'"{e.ask}": {{"x": 0, "y": 0}}' for e in elements)
    return (
        "Esta es una captura de la interfaz de Cisco Packet Tracer. La imagen mide "
        f"{w}x{h} pixeles; el origen (0,0) es su esquina superior izquierda.\n\n"
        "1) Indica con true/false que ESTADOS de la interfaz estan presentes ahora mismo:\n"
        f"{st_lines}\n\n"
        "2) Para cada elemento cuyo estado sea true, devuelve su posicion en PIXELES DE "
        f"ESTA IMAGEN:\n{el_lines}\n\n"
        "No adivines: si un estado es false, o no ves el elemento con seguridad, usa null.\n"
        "Responde SOLO con un objeto JSON, sin texto ni markdown, con este formato "
        f'exacto: {{"states": {{{ex_states}}}, "points": {{{ex_points}}}}}'
    )


def ask_points(cfg, img, sent_size, names, descs=None):
    """Pregunta a la IA por `names` sobre `img` (enviada a sent_size). -> (puntos, avisos)."""
    text = call_vision_api(cfg, png_b64(img, sent_size),
                           build_prompt(names, sent_size, descs))
    return parse_ai_response(text, sent_size, names)


def ask_multi(cfg, img, sent_size, elements):
    """Una sola llamada: estados de UI + puntos. -> (puntos por ai_name, estados, avisos)."""
    text = call_vision_api(cfg, png_b64(img, sent_size),
                           build_multi_prompt(elements, sent_size))
    states = list(dict.fromkeys(e.state for e in elements))
    return parse_multi_response(text, sent_size, [e.ask for e in elements], states)


# =====================================================================
# Recortes de referencia + verificacion con matchTemplate
# =====================================================================
def _gray(img):
    import numpy as np
    return np.asarray(img.convert("L"), dtype=np.uint8)


def make_template(shot, point_px, size=TEMPLATE_SIZE):
    """
    Recorte cuadrado de `size` px de la captura centrado en point_px (en px de captura,
    desplazado para no salirse). Devuelve (imagen, (x0, y0), (dx, dy)) donde (x0, y0) es
    su esquina en la captura y (dx, dy) la posicion del punto dentro del recorte.
    """
    size = min(size, shot.width, shot.height)
    x0 = int(min(max(point_px[0] - size // 2, 0), shot.width - size))
    y0 = int(min(max(point_px[1] - size // 2, 0), shot.height - size))
    img = shot.crop((x0, y0, x0 + size, y0 + size))
    return img, (x0, y0), (int(point_px[0] - x0), int(point_px[1] - y0))


def match_template(shot, template):
    """(confianza, (x, y) esquina hallada). Confianza 0.0 si el recorte es plano."""
    import cv2
    import numpy as np
    t = _gray(template)
    if float(t.std()) < MIN_TEMPLATE_STD:
        return 0.0, (0, 0)  # recorte sin informacion: coincidiria en cualquier sitio
    res = cv2.matchTemplate(_gray(shot), t, cv2.TM_CCOEFF_NORMED)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    _mn, mx, _mnl, mxl = cv2.minMaxLoc(res)
    return float(mx), (int(mxl[0]), int(mxl[1]))


def save_reference(fname, template, dry_run):
    """Guarda el recorte en reference_images/<fname> (en dry-run, en un temporal)."""
    folder = tempfile.mkdtemp(prefix="pt_autocal_") if dry_run else REFERENCE_IMAGES_DIR
    os.makedirs(folder, exist_ok=True)
    template.save(os.path.join(folder, fname))
    return fname


def _zoom_rect(point, screen_size):
    """Region de reintento [l,t,w,h] (unidades de pantalla) centrada en point, dentro de pantalla."""
    sw, sh = screen_size
    w, h = min(ZOOM_W, sw), min(ZOOM_H, sh)
    l = int(min(max(point[0] - w // 2, 0), sw - w))
    t = int(min(max(point[1] - h // 2, 0), sh - h))
    return [l, t, w, h]


def verify_and_refine(el, point, shot, ppu, screen_size, cfg, dry_run, log=emit):
    """
    Verifica `point` (pantalla) del Element `el`, con hasta MAX_RETRIES reintentos de
    refinamiento por IA sobre un recorte ampliado. `shot`/`ppu` es la captura de la que
    se corta el recorte. Devuelve el dict de estado del elemento.
    """
    attempts = 0
    while True:
        tmpl, corner, offset = make_template(shot, (point[0] * ppu, point[1] * ppu))
        fresh, ppu2 = capture()  # captura NUEVA: el recorte debe re-encontrarse ahi
        conf, found = match_template(fresh, tmpl)
        if evaluate_match(conf, found, corner):
            fname = save_reference(el.fname, tmpl, dry_run)
            return {"status": "ok", "point": list(point), "confidence": round(conf, 3),
                    "template": fname, "template_offset": list(offset),
                    "template_corner": list(corner), "attempts": attempts}
        log(f"    {el.name}: confianza {conf:.2f} (min {MIN_CONFIDENCE}) en {tuple(point)}")
        if attempts >= MAX_RETRIES:
            return {"status": "manual", "point": list(point), "confidence": round(conf, 3),
                    "reason": "confianza baja tras reintentos", "attempts": attempts}
        attempts += 1
        log(f"    {el.name}: reintento {attempts}/{MAX_RETRIES} con recorte ampliado...")
        rect = _zoom_rect(point, screen_size)
        crop, crop_px = crop_units(fresh, ppu2, rect)
        sent = (crop_px[0] * 2, crop_px[1] * 2)  # ampliar x2 para que la IA vea detalle
        pts, _warns = ask_points(cfg, crop, sent, (el.ask,), {el.ask: el.desc})
        if el.ask not in pts:
            return {"status": "manual", "point": list(point), "confidence": round(conf, 3),
                    "reason": "la IA no pudo afinar la posicion", "attempts": attempts}
        upp = compute_units_per_px(crop_px, sent, ppu2)
        point = list(image_to_screen(pts[el.ask][0], pts[el.ask][1], rect[:2], upp))
        shot, ppu = fresh, ppu2


def verify_cached(meta, elements, shot):
    """Re-busca los recortes guardados en `shot`. -> {nombre: (coincide, confianza|None)}."""
    from PIL import Image
    out = {}
    recs = (meta or {}).get("elements") or {}
    for el in elements:
        rec = recs.get(el.name) or {}
        path = os.path.join(REFERENCE_IMAGES_DIR, rec.get("template") or "")
        if not rec.get("template") or not os.path.exists(path):
            out[el.name] = (False, None)
            continue
        conf, found = match_template(shot, Image.open(path))
        out[el.name] = (evaluate_match(conf, found, rec.get("template_corner") or [0, 0]), conf)
    return out


def _env_matches(meta, env):
    return (isinstance(meta, dict)
            and list(meta.get("resolution") or []) == list(env["resolution"])
            and isinstance(meta.get("dpi_scale"), (int, float))
            and abs(meta["dpi_scale"] - env["dpi_scale"]) <= DPI_TOLERANCE
            and _rect_close(meta.get("window"), env["window"], WINDOW_TOLERANCE))


def _manual_hint(el):
    if el.file == "coords":
        return f"calibralo a mano en la pestana Calibracion ({el.name})"
    return {"cable": "calibralo a mano en la pestana Calibracion (cables)",
            "ip": "calibralo a mano en la pestana Calibracion (ventana IP)"}[el.file]


STATUS_LABEL = {"ok": "OK", "manual": "requiere manual", "unverified": "sin verificar"}


# =====================================================================
# Orquestacion
# =====================================================================
def filtered_point_error(point, search_point, min_above=FILTERED_MIN_ABOVE,
                         max_above=FILTERED_MAX_ABOVE, max_dx=FILTERED_MAX_DX):
    """
    None si el punto de `filtered_result` es plausible; si no, el motivo del rechazo.
    Debe estar ENCIMA del centro del buscador (fila de resultados) y dentro del ancho del
    panel de dispositivos (|dx| <= max_dx). Uno al nivel del buscador o por debajo es la lista
    de dispositivos o el propio campo, no un resultado.
    """
    x, y = point
    sx, sy = search_point
    if y > sy - min_above:
        return (f"el punto ({x}, {y}) no esta encima del buscador (y={sy}): "
                "el resultado debe estar en la fila de arriba")
    if y < sy - max_above:
        return f"el punto ({x}, {y}) esta demasiado arriba del buscador (y={sy})"
    if abs(x - sx) > max_dx:
        return (f"el punto ({x}, {y}) cae fuera del ancho del panel de dispositivos "
                f"(x={sx}+-{max_dx})")
    return None


def _calibrate_filtered(el, results, cfg, env, test_model, dry_run, log, shot_ppu=None):
    """
    filtered_result automatico: clic en search_field, escribe un modelo de prueba, espera,
    nueva captura y pide a la IA SOLO el primer resultado filtrado. Siempre limpia el buscador.
    """
    sp = results["search_field"]["point"]
    if dry_run:
        log("  [dry-run] filtered_result: NO se escribe en el buscador; se busca el resultado "
            "en la captura actual (si ya filtraste a mano, lo ubica; si no, queda sin ver).")
        if shot_ppu is None:
            return {"status": "unverified", "reason": "dry-run: no se escribio en la app"}
        shot, ppu = shot_ppu
        crop, crop_px = crop_units(shot, ppu, env["window"])
        sent = compute_send_size(*crop_px)
        pts, _w = ask_points(cfg, crop, sent, (el.ask,), {el.ask: FILTERED_RESULT_DESC})
        if el.ask not in pts:
            return {"status": "unverified",
                    "reason": "dry-run: no hay resultados filtrados visibles en la captura"}
        upp = compute_units_per_px(crop_px, sent, ppu)
        pt = list(image_to_screen(pts[el.ask][0], pts[el.ask][1], env["window"][:2], upp))
        bad = filtered_point_error(pt, sp)
        if bad:
            log(f"  [!] filtered_result rechazado: {bad}")
            return {"status": "manual", "point": pt, "reason": bad, "rejected": True}
        return {"status": "unverified", "point": pt,
                "reason": "dry-run: detectado, sin verificar ni guardar"}
    from core import dpi_aware  # noqa: F401  fija la DPI awareness; debe importarse antes de pyautogui
    import time
    import pyautogui

    def clear_box():
        pyautogui.click(sp[0], sp[1])
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("delete")

    log(f"  filtered_result: escribiendo '{test_model}' en el buscador...")
    try:
        clear_box()
        pyautogui.write(test_model, interval=0.05)
        time.sleep(FILTER_WAIT)
        shot, ppu = capture()
        crop, crop_px = crop_units(shot, ppu, env["window"])
        sent = compute_send_size(*crop_px)
        desc = (f"centro de {FILTERED_RESULT_DESC} (tras escribir '{test_model}' en el buscador)")
        pts, _w = ask_points(cfg, crop, sent, (el.ask,), {el.ask: desc})
        if el.ask not in pts:
            return {"status": "manual", "reason": "la IA no vio ningun resultado filtrado"}
        upp = compute_units_per_px(crop_px, sent, ppu)
        pt = list(image_to_screen(pts[el.ask][0], pts[el.ask][1], env["window"][:2], upp))
        bad = filtered_point_error(pt, sp)
        if bad:
            log(f"  [!] filtered_result rechazado: {bad}")
            return {"status": "manual", "point": pt, "reason": bad, "rejected": True}
        return verify_and_refine(el._replace(desc=desc), pt, shot, ppu, env["resolution"],
                                 cfg, dry_run, log)
    finally:
        clear_box()  # deja el buscador vacio pase lo que pase
        log("  filtered_result: buscador limpiado.")


def _print_table(rows, log):
    log(f"  {'elemento':<24}{'archivo':<8}estado")
    log("  " + "-" * 56)
    for name, f, st in rows:
        log(f"  {name:<24}{f:<8}{STATUS_LABEL[st]}")


def run_autocalibrate(dry_run=False, force=False, groups=GROUPS, test_model=TEST_MODEL,
                      log=emit, detected_out=None):
    """
    Ejecuta la autocalibracion de los `groups` (main = coords.json, cable =
    cable_coords.json, ip = ip_config_coords.json). Devuelve 0 si todo quedo calibrado
    (o la cache era valida), 1 si quedan elementos por calibrar o falta abrir algun
    estado de la UI. Lanza AutoCalibrateError ante problemas de config / red / API.
    detected_out (dict, opcional): se llena con {nombre: {"point": [x, y], "rejected": bool}}
    de cada punto que la IA ubico (tambien en dry-run), para dibujarlos en un overlay.
    """
    import copy
    from core import coords as coords_io
    import pyautogui

    files = list(dict.fromkeys(GROUP_FILE[g] for g in groups))
    datas = {f: coords_io.load_coords(_file_paths()[f]) for f in files}
    cable_data = datas.get("cable") or coords_io.load_coords(_file_paths()["cable"])
    registry = build_registry(cable_data)
    els = select_elements(registry, groups)
    mouse = tuple(pyautogui.position())  # para list_offset (clic previo en el dispositivo)

    env, win_warn = current_env()
    log(f"  Resolucion : {tuple(env['resolution'])}   Escala DPI: {env['dpi_scale']}")
    log(f"  Ventana PT : {env['window']}   Grupos: {', '.join(groups)}")
    if win_warn:
        log(f"  [!] {win_warn}")
    shot, ppu = capture()
    provider, model_id = current_ai()
    env = dict(env, provider=provider, model=model_id)   # la cache depende de proveedor+modelo

    # --- cache: sin API si nada cambio y los recortes siguen en su sitio ---------------
    why = "--force"
    if not force:
        hit = True
        for f in files:
            fels = [e for e in els if e.file == f]
            meta = datas[f].get(META_KEY)
            have = {e.name for e in fels if get_path(datas[f], e.path) is not None}
            ok, why = cache_decision(meta, env, [e.name for e in fels if e.required],
                                     [e.name for e in fels if e.soft], have)
            if ok:
                res = verify_cached(meta, [e for e in fels if e.required], shot)
                bad = [n for n, (m, c) in res.items() if not m]
                if bad:
                    ok, why = False, "los recortes ya no coinciden: " + ", ".join(bad)
            if not ok:
                hit, why = False, f"{f}: {why}"
                break
        if hit:
            log("  CACHE VALIDA (resolucion, escala y ventana sin cambios; recortes "
                "verificados): no se llama a la API.")
            return 0
    log(f"  Cache no aplicable: {why}")

    cfg = load_config()
    creds = cfg
    log(f"  Proveedor: {ai_providers.label(cfg.provider)}   Modelo: {cfg.model}")

    # --- una llamada: estados de UI + puntos --------------------------------------------
    ai_els = [e for e in els if e.name != "filtered_result"]
    crop, crop_px = crop_units(shot, ppu, env["window"])
    sent = compute_send_size(*crop_px)
    log(f"  Enviando captura {crop_px[0]}x{crop_px[1]} (redimensionada a {sent[0]}x{sent[1]})...")
    pts, states, warns = ask_multi(cfg, crop, sent, ai_els)
    reasons = {w.split(':')[0]: w for w in warns}
    for w in warns:
        if 'rechazada' in w or w.startswith('coordenadas normalizadas'):
            log(f"  [!] {w}")
    upp = compute_units_per_px(crop_px, sent, ppu)
    log("  Estados de UI detectados:")
    for s in dict.fromkeys(e.state for e in ai_els):
        log(f"    {'SI' if states.get(s) else 'NO'}  {s}")
    absent = missing_states(ai_els, states)
    for s, names in absent.items():
        log(f"  [!] FALTA ({s}): {STATE_HINTS[s]}")
        log(f"      afecta a: {', '.join(names)}")

    results = {}
    log("  Verificando con matchTemplate...")
    for e in ai_els:
        if not states.get(e.state):
            continue  # no se adivina: se avisa arriba
        if e.ask not in pts:
            results[e.name] = {"status": "manual",
                               "reason": reasons.get(e.ask, "no detectado por la IA")}
            continue
        sp_ = list(image_to_screen(pts[e.ask][0], pts[e.ask][1], env["window"][:2], upp))
        results[e.name] = verify_and_refine(e, sp_, shot, ppu, env["resolution"],
                                            creds, dry_run, log)
        r = results[e.name]
        log(f"    {e.name:<24} {r['status'].upper():<7} conf={r.get('confidence', '-')}")

    # --- geometria de la lista de interfaces (derivada de los items 0 y 1) ---------------
    derived = {}
    r0, r1 = results.get("list_offset"), results.get("list_row_height")
    if r0 or r1:
        if r0 and r1 and r0["status"] == r1["status"] == "ok":
            try:
                off, row_h = derive_menu_geometry(r0["point"], r1["point"], mouse)
                derived = {"list_offset": off, "list_row_height": row_h}
                log(f"    lista de interfaces: offset={off} fila={row_h}px (mouse en {mouse})")
            except ValueError as err:
                for r in (r0, r1):
                    r.update(status="manual", reason=str(err))
                log(f"    [!] {err}")
        else:
            for r in (r0, r1):
                if r:
                    r.update(status="manual",
                             reason=r.get("reason") or "faltan los dos primeros items de la lista")

    # --- filtered_result automatico -------------------------------------------------------
    fr = registry.get("filtered_result")
    if fr is not None and fr in els:
        has = get_path(datas["coords"], fr.path) is not None
        sp_ok = results.get("search_field", {}).get("status") == "ok"
        busy = states.get("interface_menu") or states.get("ip_window")
        if not sp_ok:
            log("  filtered_result omitido: search_field no esta verificado.")
        elif busy:
            log("  filtered_result omitido: hay un menu/ventana abierto (cierralo y reintenta).")
        elif has and not force:
            log("  filtered_result omitido: ya tiene valor (usa --force para recalcularlo).")
        else:
            results["filtered_result"] = _calibrate_filtered(
                fr, results, creds, env, test_model, dry_run, log, (shot, ppu))
            r = results["filtered_result"]
            log(f"    {'filtered_result':<24} {r['status'].upper():<7} conf={r.get('confidence', '-')}")

    if detected_out is not None:
        detected_out.clear()
        for name, r in results.items():
            if r.get("point"):
                detected_out[name] = {"point": list(r["point"]), "rejected": bool(r.get("rejected"))}

    # --- construir el resultado por archivo -------------------------------------------------
    outputs, table, unresolved = {}, [], []
    for f in files:
        data = copy.deepcopy(datas[f])
        old_meta = datas[f].get(META_KEY)
        same_env = _env_matches(old_meta, env)
        records = {}
        for e in (x for x in els if x.file == f):
            r = results.get(e.name)
            if r and r["status"] == "ok":
                set_path(data, e.path, derived.get(e.name, r["point"]))
                records[e.name] = r
            elif r:  # manual: se conserva el valor previo, si lo hay
                records[e.name] = r
            else:
                old = ((old_meta or {}).get("elements") or {}).get(e.name) if same_env else None
                if old:
                    records[e.name] = old
                elif get_path(data, e.path) is not None:
                    records[e.name] = {"status": "unverified",
                                       "reason": "no visible en esta ejecucion"}
            st = element_status(get_path(data, e.path) is not None, records.get(e.name))
            table.append((e.name, f, st))
            if st == "manual" and (e.name in results or e.state not in absent):
                unresolved.append(e)
        data[META_KEY] = {"version": META_VERSION, "resolution": env["resolution"],
                          "dpi_scale": env["dpi_scale"], "window": env["window"],
                          "provider": cfg.provider, "model": cfg.model, "elements": records}
        outputs[f] = data

    log("")
    _print_table(table, log)
    if dry_run:
        log("\n  Dry-run: NO se guardo nada.")
    else:
        for f, data in outputs.items():
            if not coords_io.save_coords(_file_paths()[f], data):
                raise AutoCalibrateError(f"no se pudo guardar {_file_paths()[f]}")
    code = 0
    if unresolved:
        code = 1
        log("\n  REQUIEREN CALIBRACION MANUAL:")
        for e in unresolved:
            log(f"    {e.name:<24} -> {_manual_hint(e)}")
    if absent:
        code = 1
        log("\n  Faltan estados de la UI (no se adivino nada). Preparalos y reejecuta con "
            "solo ese grupo:")
        for s, names in absent.items():
            log(f"    {s}: {STATE_HINTS[s]}")
    if code == 0:
        log("\n  Autocalibracion completa.")
    return code


def run_check(groups=GROUPS, dry_run=False, log=emit, table_out=None):
    """
    --check: SIN API. Re-verifica con matchTemplate todos los puntos guardados y reporta
    cuales ya no coinciden. Actualiza el estado guardado salvo en dry-run.
    Devuelve 1 si algun elemento queda "requiere manual", si no 0.
    """
    from core import coords as coords_io

    files = list(dict.fromkeys(GROUP_FILE[g] for g in groups))
    datas = {f: coords_io.load_coords(_file_paths()[f]) for f in files}
    registry = build_registry(datas.get("cable") or coords_io.load_coords(_file_paths()["cable"]))
    els = select_elements(registry, groups)
    env, win_warn = current_env()
    log(f"  Resolucion : {tuple(env['resolution'])}   Escala DPI: {env['dpi_scale']}")
    log(f"  Ventana PT : {env['window']}")
    if win_warn:
        log(f"  [!] {win_warn}")
    shot, _ = capture()

    table, stale, changed_files = [], [], {}
    for f in files:
        data, meta = datas[f], datas[f].get(META_KEY)
        if meta and not _env_matches(meta, env):
            log(f"  [!] {f}: la resolucion/escala/ventana cambio respecto a la calibracion "
                f"({meta.get('resolution')}, DPI {meta.get('dpi_scale')}, ventana {meta.get('window')}).")
        fels = [e for e in els if e.file == f]
        res = verify_cached(meta, fels, shot) if meta else {}
        new_recs = dict((meta or {}).get("elements") or {})
        for e in fels:
            has = get_path(data, e.path) is not None
            rec = new_recs.get(e.name)
            if has and rec and rec.get("template") and e.name in res:
                matched, conf = res[e.name]
                st = check_status(matched, e.state)
                if not matched:
                    stale.append((e, conf))
                rec = dict(rec, status=st)
                if matched:
                    rec.pop("reason", None)
                else:
                    rec["reason"] = "no coincide en --check"
                if new_recs.get(e.name) != rec:
                    changed_files[f] = True
                new_recs[e.name] = rec
            st = element_status(has, new_recs.get(e.name))
            table.append((e.name, f, st))
        if meta:
            data[META_KEY] = dict(meta, elements=new_recs)

    _print_table(table, log)
    if table_out is not None:
        table_out.extend(table)
    if stale:
        log("\n  Ya NO coinciden (resolucion / layout cambiaron o la pantalla no esta abierta):")
        for e, conf in stale:
            extra = "" if e.state == "main" else f"  (necesita estado '{e.state}': {STATE_HINTS[e.state]})"
            log(f"    {e.name:<24} confianza={'-' if conf is None else f'{conf:.2f}'}{extra}")
    if dry_run:
        log("\n  Dry-run: no se actualizo el estado guardado.")
    else:
        for f in changed_files:
            coords_io.save_coords(_file_paths()[f], datas[f])
    bad = [n for n, _f, st in table if st == "manual"]
    if bad:
        log("\n  Requieren recalibrar: " + ", ".join(bad) + "   (Autocalibrar, en la pestana Calibracion)")
        return 1
    log("\n  Todo lo verificable coincide.")
    return 0


def collect_status(groups=GROUPS):
    """
    Estado por elemento, SIN tocar la pantalla ni la API (lo usa el panel).
    Devuelve [{"name","file","group","state","status","label"}].
    """
    from core import coords as coords_io
    datas = {f: coords_io.load_coords(p) for f, p in _file_paths().items()}
    registry = build_registry(datas["cable"])
    rows = []
    for e in select_elements(registry, groups):
        data = datas[e.file]
        recs = (data.get(META_KEY) or {}).get("elements") or {}
        st = element_status(get_path(data, e.path) is not None, recs.get(e.name))
        rows.append({"name": e.name, "file": e.file, "group": e.group, "state": e.state,
                     "status": st, "label": STATUS_LABEL[st]})
    return rows
