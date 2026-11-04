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


def needs_ip_config(text):
    """True si la topologia (sintaxis por redes) tiene PCs con IP que se configuraran."""
    if not text or not is_grouped_syntax(text):
        return False
    try:
        parsed = parse_grouped(text)
    except PTError:
        return False
    return any(pc.get("ip") for red in parsed["redes"] for pc in red["pcs"])


def required_names(text):
    names = list(MAIN_NAMES)
    if needs_ip_config(text):
        names += list(IP_NAMES)
    return names


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


def run_preflight(text, *, verify_screen=False, log=None):
    """
    Preflight para `text`. verify_screen=True re-verifica con matchTemplate los puntos de
    pantalla principal (captura de pantalla; NO usa la API ni mueve el mouse).
    """
    log = log or emit
    names = required_names(text)
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
