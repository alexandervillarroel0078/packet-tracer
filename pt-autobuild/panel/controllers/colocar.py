"""Controlador de la pestana Colocar/Construir (sin tkinter)."""

import json
import os
from dataclasses import dataclass, field

from automation import build, move_device
from core import paths, preflight
from core.errors import PTError
from core.log import capture
from core.topology import TopologyFileError, load_topology

# Acciones que pueden mover el mouse (todas con dry_run=True por defecto).
MOUSE_ACTIONS = ("build", "recalibrate_and_continue", "move_device")


@dataclass
class PreviewResult:
    lines: list = field(default_factory=list)
    ok: bool = True
    error: str = ""

    def text(self):
        return "\n".join(self.lines)


@dataclass
class BuildOutcome:
    status: str                      # "started" | "blocked" | "busy"
    preflight: object = None         # PreflightResult si se evaluo


class ColocarController:
    def __init__(self, shared):
        self.shared = shared
        self.last_preflight = None

    # ----- entrada de la topologia ------------------------------------------
    def list_examples(self):
        try:
            return sorted(f for f in os.listdir(paths.EXAMPLES_DIR) if f.lower().endswith(".txt"))
        except OSError:
            return []

    def load_example(self, name):
        path = os.path.join(paths.EXAMPLES_DIR, os.path.basename(name))
        return self.load_file(path)

    @staticmethod
    def load_file(path):
        """
        Lee una topologia de un .txt o de un .json. El JSON puede ser el registro que genera
        la propia herramienta (usa su 'comando_original') o un objeto con 'topologia'/'texto'.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            raise PTError(f"no se pudo leer {path}: {e}") from e
        if not path.lower().endswith(".json"):
            return raw
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise PTError(f"JSON invalido en {os.path.basename(path)}: {e}") from e
        if isinstance(data, dict):
            for key in ("comando_original", "topologia", "texto"):
                if isinstance(data.get(key), str) and data[key].strip():
                    return data[key]
        if isinstance(data, str) and data.strip():
            return data
        raise PTError("el JSON no trae el texto de la topologia (se esperaba "
                      "'comando_original', 'topologia' o 'texto').")

    # ----- vista previa y preflight (sin mouse) ------------------------------------
    def preview(self, text):
        """Plan de colocacion SIN actuar (dry-run). Rapido: corre en el hilo de la interfaz."""
        lines = []
        try:
            with capture(lines.append):
                build.build_topology(text, dry_run=True, log=lines.append)
        except PTError as e:
            return PreviewResult(lines, False, str(e))
        return PreviewResult(lines, True)

    def check_preflight(self, text, verify_screen=False, action=None):
        """
        Preflight de calibracion. verify_screen=True re-verifica en pantalla (sin API).
        `action` ("build"/"ip"/"cable") limita la comprobacion a los puntos de esa accion.
        """
        lines = []
        with capture(lines.append):
            self.last_preflight = preflight.run_preflight(text, verify_screen=verify_screen,
                                                          log=lines.append, action=action)
        return self.last_preflight, lines

    def start_preflight(self, text):
        """Preflight completo (con captura de pantalla) en un hilo; resultado en last_preflight."""
        def job(ctx):
            self.last_preflight = preflight.run_preflight(text, verify_screen=True, log=ctx.log)
        return self.shared.runner.start("Comprobar calibracion", job, touches_mouse=False)

    # ----- construir ---------------------------------------------------------------
    def _need_text(self, text):
        if not (text or "").strip():
            raise PTError("escribe o carga una topologia primero.")

    def build(self, text, dry_run=True):
        """
        Dry-run: calcula y muestra el plan (no mueve el mouse). Real: antes pasa el preflight;
        si falla, NO actua y devuelve BuildOutcome('blocked'); la vista ofrece "Recalibrar y
        continuar". Con exito, cuenta regresiva visible y colocacion en un hilo.
        """
        self._need_text(text)
        runner = self.shared.runner
        if runner.busy:
            return BuildOutcome("busy")
        if not dry_run:
            result, _ = self.check_preflight(text, verify_screen=False, action="build")
            if not result.ok:
                return BuildOutcome("blocked", result)

        def job(ctx):
            return build.build_topology(text, dry_run=dry_run, countdown=0, log=ctx.log,
                                        cancel=ctx.cancel, progress=ctx.progress)

        label = "Vista previa del plan (dry-run)" if dry_run else "CONSTRUIR topologia"
        started = runner.start(label, job, touches_mouse=not dry_run,
                               countdown=0 if dry_run else self.shared.seconds())
        return BuildOutcome("started" if started else "busy", self.last_preflight)

    def recalibrate_and_continue(self, text, dry_run=True):
        """
        Tras un preflight fallido: autocalibra los grupos que faltan (IA) y, si queda todo
        listo, construye. Con dry_run=True solo muestra lo que detectaria la IA y el plan.
        """
        from automation import calibrate
        self._need_text(text)
        groups = (self.last_preflight.groups if self.last_preflight else None) or ("main",)

        def job(ctx):
            ctx.log(f"  Recalibrando ({', '.join(groups)})...")
            calibrate.auto_calibrate(dry_run=dry_run, groups=list(groups), log=ctx.log)
            if dry_run:
                ctx.log("  Dry-run: no se guardo nada ni se construye.")
                return None
            result = preflight.run_preflight(text, verify_screen=False, log=ctx.log,
                                             action="build")
            self.last_preflight = result
            if not result.ok:
                raise PTError("sigue sin estar calibrado: " + ", ".join(result.blocking)
                              + ". Completa los pasos de la pestana Calibracion.")
            return build.build_topology(text, dry_run=False, countdown=0, log=ctx.log,
                                        cancel=ctx.cancel, progress=ctx.progress)

        label = ("Recalibrar (solo mostrar)" if dry_run else "Recalibrar y continuar")
        return self.shared.runner.start(label, job, touches_mouse=not dry_run,
                                        countdown=0 if dry_run else self.shared.seconds())

    # ----- mover dispositivo -----------------------------------------------------------
    def list_devices(self):
        try:
            topo = load_topology(paths.TOPOLOGY_ACTUAL_PATH)
        except TopologyFileError:
            return []
        return [d.get("nombre", "?") for d in topo.get("dispositivos", [])]

    def move_device(self, name, x=None, y=None, random_pos=False, dry_run=True):
        if not (name or "").strip():
            raise PTError("elige el dispositivo a mover.")
        xi = yi = None
        if not random_pos:
            try:
                xi, yi = int(x), int(y)
            except (TypeError, ValueError):
                raise PTError("X e Y deben ser numeros enteros (o marca posicion aleatoria).")

        def job(ctx):
            return move_device.move_device(name, xi, yi, random_pos=random_pos, dry_run=dry_run,
                                           countdown=0, log=ctx.log, cancel=ctx.cancel)

        label = f"Mover {name}" + (" (dry-run)" if dry_run else "")
        return self.shared.runner.start(label, job, touches_mouse=not dry_run,
                                        countdown=0 if dry_run else self.shared.seconds())
