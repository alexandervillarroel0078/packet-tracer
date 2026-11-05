"""
Boton unico "Calibrar" (sin tkinter): lo usan la pestana Simple y Avanzado > Calibracion.

Flujo: 1) verifica la pantalla SIN API y sin tocar el mouse; 2) si todo coincide dice
"Ya está calibrado"; 3) si no, autocalibra SOLO el grupo main (con cuenta regresiva y aviso
previo, porque escribe en el buscador) y resume en lenguaje simple que quedo bien y que hay
que hacer a mano.
"""

from automation import calibrate
from core import autocalibrate as ac
from core import preflight, settings
from core.errors import PTError

# Acciones que pueden mover el mouse (todas con dry_run=True por defecto).
MOUSE_ACTIONS = ("calibrate",)

ALREADY_OK = "Ya está calibrado."

SEARCH_NOTICE = [
    "[!] Ojo: voy a hacer clic en el buscador de Packet Tracer y a escribir un modelo de "
    "prueba (2911) para ubicar el primer resultado; lo borro después.",
    "    No toques el mouse ni el teclado hasta que termine. "
    "DETENER o mouse a la esquina superior izquierda = abortar.",
]


def search_notice(groups, dry_run):
    """Aviso para la cuenta regresiva: solo main escribe en el buscador (filtered_result)."""
    if dry_run or "main" not in (groups or ()):
        return None
    return list(SEARCH_NOTICE)


def calibration_steps():
    return ["Voy a calibrar Packet Tracer automaticamente:",
            "  1. Tomo una captura de la pantalla (Packet Tracer debe verse completo).",
            "  2. Se la envio a la IA para que ubique el buscador y el area de trabajo.",
            "  3. Escribo un modelo de prueba en el buscador para ubicar el primer "
            "resultado y lo borro despues.",
            "  4. Compruebo que cada punto quedo bien."]


def require_key():
    if not settings.read_settings().get("has_key"):
        raise PTError("falta la clave de la IA. Ponla en la pestaña Ajustes para poder "
                      "calibrar automaticamente.")


def main_result():
    """Estado de lo necesario para construir (grupo main), sin pantalla ni API."""
    return preflight.evaluate(ac.collect_status(("main",)), preflight.required_names("", "build"))


def result_summary(result=None):
    """Lineas en lenguaje simple: que quedo bien y que hay que hacer a mano."""
    result = result or main_result()
    good = [n for n, st, _ in result.items if st != "manual"]
    lines = []
    if good:
        lines.append("Quedó bien: " + preflight.plain_list(good) + ".")
    if result.blocking:
        lines.append("Hay que hacerlo a mano: " + preflight.plain_list(result.blocking) + ". "
                     "Ve a Avanzado > Calibración > Herramientas de depuración y usa "
                     "«Capturar punto» (mueve el mouse al punto y pulsa F8).")
    else:
        lines.append("La calibración está lista.")
    return lines


class CalibrarController:
    def __init__(self, shared):
        self.shared = shared

    # ----- estado resumido (sin pantalla ni API) ----------------------------------------
    def status_text(self):
        result = main_result()
        if result.ok:
            return "Calibración lista."
        return result.plain_summary() + " Pulsa Calibrar."

    @staticmethod
    def last_calibration_path():
        """Captura enviada a la IA con los puntos devueltos (None si aun no hay)."""
        from panel.controllers.visible import VisibleController
        return VisibleController.last_calibration()

    # ----- Calibrar --------------------------------------------------------------------
    def calibrate(self, dry_run=True):
        """
        Verifica sin API; si no coincide, autocalibra el grupo main. Con dry-run solo verifica
        y explica lo que haria. Devuelve True si arranco la comprobacion.
        """
        runner = self.shared.runner
        if runner.busy:
            return False

        def verify(ctx):
            ctx.log("Compruebo la pantalla de Packet Tracer (sin IA y sin tocar el mouse)...")
            table = []
            # en dry-run no se actualiza el estado guardado
            ac.run_check(groups=("main",), dry_run=dry_run, log=lambda m: None, table_out=table)
            rows = [{"name": n, "status": st} for n, _f, st in table]
            result = preflight.evaluate(rows, preflight.required_names("", "build"))
            if result.ok:
                ctx.log(ALREADY_OK)
            else:
                ctx.log("Falta calibrar: " + preflight.plain_list(result.blocking) + ".")
            return result

        def after(status, result):
            if status == "ok" and result is not None and not result.ok:
                self._autocalibrate_main(dry_run)

        return runner.start("Comprobar calibración", verify, touches_mouse=False,
                            on_done=after)

    def _autocalibrate_main(self, dry_run):
        runner = self.shared.runner
        steps = calibration_steps()
        if dry_run:
            def explain(ctx):
                for line in steps:
                    ctx.log(line)
                ctx.log("Dry-run: no calibré nada. Desmarca Dry-run y pulsa Calibrar de nuevo.")
            return runner.start("Calibrar (solo explica)", explain)
        try:
            require_key()
        except PTError as e:
            runner.log(f"[ERROR] {e}")
            return False

        def job(ctx):
            calibrate.auto_calibrate(dry_run=False, groups=["main"], log=ctx.log)
            ctx.log("")
            for line in result_summary():
                ctx.log(line)

        return runner.start("Calibrar", job, touches_mouse=True,
                            countdown=self.shared.seconds(),
                            notice=steps + search_notice(["main"], False))
