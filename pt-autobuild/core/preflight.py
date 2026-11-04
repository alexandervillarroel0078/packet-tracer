"""
core.preflight - comprobacion de calibracion antes de construir.

    required_names(text)            -> elementos que la topologia necesita calibrados
    evaluate(rows, names)           -> PreflightResult (logica pura)
    run_preflight(text, ...)        -> PreflightResult, leyendo data/ (y opcionalmente
                                       re-verificando en pantalla, SIN API y sin mouse)

Estados por elemento: "ok", "unverified" (hay valor pero no se verifico: no bloquea) y
"manual" (falta el valor o dejo de coincidir: bloquea).
"""

from dataclasses import dataclass, field

from core import autocalibrate as ac
from core.errors import PTError
from core.log import emit
from core.topology import is_grouped_syntax, parse_grouped

MAIN_NAMES = ("search_field", "filtered_result", "canvas_top_left", "canvas_bottom_right")
IP_NAMES = ("desktop_tab", "ip_configuration_item", "static_radio", "close_button",
            "ipv4_address", "subnet_mask", "default_gateway")
CABLE_NAMES = ("cable_icon", "list_offset", "list_row_height")
ACTION_NAMES = {"build": MAIN_NAMES, "ip": IP_NAMES, "cable": CABLE_NAMES}


@dataclass
class PreflightResult:
    items: list = field(default_factory=list)      # [(nombre, estado, detalle)]
    groups: tuple = ()                             # grupos a recalibrar si falla

    @property
    def blocking(self):
        return [n for n, st, _ in self.items if st == "manual"]

    @property
    def warnings(self):
        return [n for n, st, _ in self.items if st == "unverified"]

    @property
    def ok(self):
        return not self.blocking

    def summary(self):
        if self.ok:
            extra = f" ({len(self.warnings)} sin verificar)" if self.warnings else ""
            return f"Calibracion lista{extra}."
        return "Falta calibrar o dejo de coincidir: " + ", ".join(self.blocking) + "."

    def plain_summary(self):
        """Resumen sin nombres internos (para la pantalla simple)."""
        if self.ok:
            return "Calibracion lista."
        return "Falta calibrar: " + plain_list(self.blocking) + "."


def needs_ip_config(text):
    """True si la topologia (sintaxis por redes) tiene PCs con IP que se configuraran."""
    if not text or not is_grouped_syntax(text):
        return False
    try:
        parsed = parse_grouped(text)
    except PTError:
        return False
    return any(pc.get("ip") for red in parsed["redes"] for pc in red["pcs"])


def required_names(text, action=None):
    """
    Puntos que necesita una accion:
        "build" -> solo el grupo main      "ip" -> solo el grupo ip
        "cable" -> solo el grupo cable     None -> todo lo que usa la topologia (main, y ip si
                                           tiene PCs con IP); es la comprobacion informativa.
    """
    if action is not None:
        if action not in ACTION_NAMES:
            raise ValueError(f"accion desconocida: {action!r}")
        return list(ACTION_NAMES[action])
    names = list(MAIN_NAMES)
    if needs_ip_config(text):
        names += list(IP_NAMES)
    return names


# Nombre interno -> como se le dice a la persona (fuera de la pestana Avanzado).
FRIENDLY = {
    "search_field": "el buscador de dispositivos",
    "filtered_result": "el icono del resultado de busqueda",
    "canvas_top_left": "la esquina superior izquierda del area de trabajo",
    "canvas_bottom_right": "la esquina inferior derecha del area de trabajo",
    "desktop_tab": "la pestana Desktop",
    "ip_configuration_item": "el icono IP Configuration",
    "static_radio": "la opcion Static",
    "close_button": "el boton de cerrar la ventana",
    "ipv4_address": "el campo de la direccion IP",
    "subnet_mask": "el campo de la mascara",
    "default_gateway": "el campo del gateway",
    "cable_icon": "el icono de cables",
    "list_offset": "la lista de interfaces",
    "list_row_height": "la lista de interfaces",
}


def plain(text):
    """Cambia los nombres internos de puntos por lenguaje simple en un mensaje."""
    import re
    for name in sorted(FRIENDLY, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}\b", FRIENDLY[name], text)
    return text


def plain_list(names):
    """'a, b y c' en lenguaje simple, sin repetidos."""
    out = list(dict.fromkeys(FRIENDLY.get(n, n) for n in names))
    if len(out) <= 1:
        return "".join(out)
    return ", ".join(out[:-1]) + " y " + out[-1]


def groups_for(names):
    reg = ac.build_registry()
    return tuple(g for g in ac.GROUPS if any(reg[n].group == g for n in names if n in reg))


def evaluate(rows, names):
    """rows = [{"name", "status", ...}] (ac.collect_status o la tabla de run_check)."""
    by_name = {r["name"]: r["status"] for r in rows}
    items = []
    for n in names:
        st = by_name.get(n, "manual")
        if n == "ip_configuration_item" and st == "manual":
            # es opcional ('skip' o ausente si aparece directo): solo avisa
            st = "unverified"
        detail = {"ok": "calibrado y verificado",
                  "unverified": "hay valor pero sin verificar",
                  "manual": "falta calibrar o no coincide"}[st]
        items.append((n, st, detail))
    return PreflightResult(items=items, groups=groups_for(names))


def run_preflight(text, *, verify_screen=False, log=None, action=None):
    """
    Preflight para `text`. verify_screen=True re-verifica con matchTemplate los puntos de
    pantalla principal (captura de pantalla; NO usa la API ni mueve el mouse).
    `action` ("build" | "ip" | "cable") limita la comprobacion a los puntos de esa accion.
    """
    log = log or emit
    names = required_names(text, action)
    groups = groups_for(names) or ("main",)
    if verify_screen:
        table = []
        ac.run_check(groups=groups, dry_run=True, log=lambda m: None, table_out=table)
        rows = [{"name": n, "status": st} for n, _f, st in table]
    else:
        rows = ac.collect_status(groups)
    result = evaluate(rows, names)
    for n, st, detail in result.items:
        log(f"  {ac.STATUS_LABEL[st]:<16} {n}")
    log("  " + result.summary())
    return result
