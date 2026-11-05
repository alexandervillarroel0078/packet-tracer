"""
Asistente de calibracion por demanda (sin tkinter) para los grupos cable e ip.

Estos grupos ya no tienen botones permanentes: cuando una accion real (Aplicar IP, cableado)
detecta que falta calibrar, llama a ensure(); si falta, NO actua y deja un Wizard pendiente
con la instruccion exacta ("Abre la ventana de IP de una PC en la pestaña Desktop"). La vista
lo muestra con un boton "Continuar" que calibra SOLO ese grupo (con cuenta regresiva y Detener).
"""

from dataclasses import dataclass, field

from automation import calibrate
from core import autocalibrate as ac
from core import preflight
from core.errors import PTError
from panel.controllers.calibrar import require_key, search_notice

# Acciones que pueden mover el mouse (todas con dry_run=True por defecto).
MOUSE_ACTIONS = ("continuar",)

GROUP_ACTION = {"ip": "ip", "cable": "cable"}

# Estado de la pantalla que hay que dejar -> instruccion exacta
INSTRUCTIONS = {
    "main": "Deja Packet Tracer visible, sin ventanas ni menús encima.",
    "ip_window": "Abre la ventana de IP de una PC en la pestaña Desktop.",
    "ip_desktop": "Abre la ventana de IP de una PC en la pestaña Desktop.",
    "ip_config": "En esa ventana, abre IP Configuration y deja marcado Static.",
    "cable_palette": "Haz clic en la categoría de conexiones (el rayo) de la paleta inferior.",
    "interface_menu": "Con un cable armado, haz clic en un dispositivo del lienzo y deja el "
                      "mouse quieto encima (la lista de interfaces debe seguir desplegada).",
}
# orden en que se piden los estados cuando faltan varios
STATE_ORDER = ("main", "ip_window", "ip_desktop", "ip_config", "cable_palette",
               "interface_menu")

GROUP_TITLE = {"ip": "la ventana de IP", "cable": "los cables"}


@dataclass
class Wizard:
    group: str
    instruction: str
    missing: list = field(default_factory=list)       # nombres internos que faltan
    names: tuple = ()                                 # lo que exige la accion

    @property
    def title(self):
        return f"Falta calibrar {GROUP_TITLE.get(self.group, self.group)}"

    @property
    def text(self):
        return (f"{self.title}: {preflight.plain_list(self.missing)}.\n"
                f"{self.instruction}\nCuando lo tengas listo, pulsa Continuar.")


def _state_of(name):
    el = ac.build_registry().get(name)
    return el.state if el else "main"


class AsistenteController:
    def __init__(self, shared):
        self.shared = shared
        self.pending = None          # Wizard o None

    # ----- deteccion ------------------------------------------------------------------------
    @staticmethod
    def missing(group, names=None):
        """Nombres que bloquean la accion del grupo (sin pantalla ni API)."""
        names = list(names or preflight.required_names("", GROUP_ACTION[group]))
        return preflight.evaluate(ac.collect_status((group,)), names).blocking

    def _wizard(self, group, missing, names):
        states = {_state_of(n) for n in missing}
        state = next((s for s in STATE_ORDER if s in states), "main")
        return Wizard(group, INSTRUCTIONS[state], list(missing), tuple(names))

    def ensure(self, group, names=None):
        """
        True si el grupo esta calibrado para la accion. Si no, deja el asistente pendiente,
        avisa en el log y devuelve False: la accion NO debe actuar.
        """
        if group not in GROUP_ACTION:
            raise ValueError(f"grupo sin asistente: {group!r}")
        names = tuple(names or preflight.required_names("", GROUP_ACTION[group]))
        missing = self.missing(group, names)
        if not missing:
            self.pending = None
            return True
        self.pending = self._wizard(group, missing, names)
        w = self.pending
        self.shared.runner.log(f"[!] {w.title}: {preflight.plain_list(w.missing)}.")
        self.shared.runner.log(f"    {w.instruction} Luego pulsa Continuar. No se movió nada.")
        return False

    def dismiss(self):
        self.pending = None

    # ----- Continuar -------------------------------------------------------------------------
    def continuar(self, dry_run=True):
        """Calibra SOLO el grupo pendiente. Con dry-run explica y no toca nada."""
        w = self.pending
        if w is None:
            raise PTError("no hay ninguna calibracion pendiente.")
        runner = self.shared.runner
        if runner.busy:
            return False
        group = w.group
        if dry_run:
            def explain(ctx):
                ctx.log(f"Voy a calibrar {GROUP_TITLE.get(group, group)} con la IA "
                        "(captura de pantalla; no hago clics).")
                ctx.log(w.instruction)
                ctx.log("Dry-run: no calibré nada. Desmarca Dry-run y pulsa Continuar.")
            return runner.start("Continuar (solo explica)", explain)
        require_key()

        def job(ctx):
            calibrate.auto_calibrate(dry_run=False, groups=[group], log=ctx.log)
            left = self.missing(group, w.names)
            if left:
                self.pending = self._wizard(group, left, w.names)
                ctx.log("[!] Todavía falta: " + preflight.plain_list(left) + ".")
                ctx.log(self.pending.instruction + " Luego pulsa Continuar otra vez.")
            else:
                self.pending = None
                ctx.log(f"Listo: {GROUP_TITLE.get(group, group)} calibrada. "
                        "Vuelve a pulsar la acción que querías hacer.")

        return runner.start(f"Calibrar {GROUP_TITLE.get(group, group)}", job,
                            touches_mouse=True, countdown=self.shared.seconds(),
                            notice=search_notice([group], False))
