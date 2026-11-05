"""
Controlador de la pantalla simple (sin tkinter): estado de una linea y el boton "Construir"
que lo hace todo en orden: comprobar calibracion, autocalibrar si falta, cuenta regresiva y
construir. Todos los mensajes van en lenguaje simple (sin nombres internos de puntos).
"""

from dataclasses import dataclass

from automation import build
from core import autocalibrate as ac
from core import preflight, settings
from core.errors import CancelledError, PTError
from panel.controllers import calibrar

# Acciones que pueden mover el mouse (todas con dry_run=True por defecto).
MOUSE_ACTIONS = ("build", "calibrate")

EXAMPLE_TEXT = "1 switch, 1 PC"


@dataclass
class StatusInfo:
    calibration_ok: bool
    calibration_text: str
    api_ok: bool
    api_text: str

    def line(self):
        return f"{self.calibration_text}    |    {self.api_text}"


class SimpleController:
    def __init__(self, shared):
        self.shared = shared
        self.last_preflight = None

    # ----- estado de una linea -----------------------------------------------------------
    def check_calibration(self):
        """Estado de la calibracion de lo necesario para construir (sin captura ni API)."""
        rows = ac.collect_status(("main",))
        self.last_preflight = preflight.evaluate(rows, preflight.required_names("", "build"))
        return self.last_preflight

    def status(self):
        ok = self.check_calibration().ok
        has_key = bool(settings.read_settings().get("has_key"))
        return StatusInfo(
            ok, "Calibración: OK" if ok else "Calibración: falta calibrar (pulsa Calibrar)",
            has_key, "API: conectada" if has_key else "API: sin clave")

    # ----- calibrar ---------------------------------------------------------------------------
    calibration_steps = staticmethod(calibrar.calibration_steps)

    def _require_key(self):
        calibrar.require_key()

    def calibrate(self, dry_run=True):
        """El unico boton de calibracion: verifica sin API y, si hace falta, autocalibra main."""
        return self.shared.calibrator.calibrate(dry_run=dry_run)

    def _finish_calibration(self, ctx):
        result = self.check_calibration()
        if not result.ok:
            raise PTError(f"no pude calibrar {preflight.plain_list(result.blocking)}. Revisa que "
                          "Packet Tracer se vea completo y reintenta; si sigue igual, usa la "
                          "pestaña Avanzado.")
        ctx.log("Calibración lista.")

    def build(self, text, dry_run=True):
        """
        Construir en orden. Antes de la cuenta regresiva comprueba la calibracion y avisa de lo
        que hara si falta. Con dry-run no mueve el mouse: solo muestra el plan (o, si falta
        calibrar, lo que haria). Devuelve True si arranco.
        """
        from automation import calibrate
        if not (text or "").strip():
            raise PTError("escribe primero la topologia (por ejemplo: " + EXAMPLE_TEXT + ").")
        runner = self.shared.runner
        if runner.busy:
            return False
        ready = self.check_calibration().ok
        if not ready:
            if not dry_run:
                self._require_key()
            runner.log("Falta calibrar Packet Tracer.")
            for line in self.calibration_steps():
                runner.log(line)

        def job(ctx):
            if not ready:
                if dry_run:
                    ctx.log("Dry-run: no calibro ni construyo. Desmarca Dry-run para hacerlo "
                            "todo de verdad.")
                    return None
                calibrate.auto_calibrate(dry_run=False, groups=["main"], log=ctx.log)
                self._finish_calibration(ctx)
            try:
                return build.build_topology(text, dry_run=dry_run, countdown=0, log=ctx.log,
                                            cancel=ctx.cancel, progress=ctx.progress)
            except CancelledError:
                raise
            except PTError as e:
                raise PTError(preflight.plain(str(e))) from e

        label = "Simulacro de construccion" if dry_run else "Construir"
        notice = None if ready else calibrar.search_notice(["main"], dry_run)
        return runner.start(label, job, touches_mouse=not dry_run,
                            countdown=0 if dry_run else self.shared.seconds(), notice=notice)

