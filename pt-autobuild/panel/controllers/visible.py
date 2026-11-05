"""
Modo visible (sin tkinter): traduce los eventos de core.log (la unica fuente) a lo que muestran
la barra de accion, el overlay y el log, y aplica los controles (velocidad, pausa, paso a paso)
sobre core.visual.state.

  VisibleModel      eventos -> texto de la barra + comandos de dibujo + linea de log
  VisibleController controles del panel -> core.visual.state
"""

import time
from collections import deque

from core import annotate
from core import visual
from core.visual import SPEEDS, SPEED_NAMES

# Comandos de dibujo para el overlay (los dibuja panel/visible_view.py).
MARK, LINE, RECT, CLEAR = "mark", "line", "rect", "clear"
GREEN, RED = "#22e34a", "#ff3b3b"
TRAIL = 4                    # fases recientes con su duracion en la barra


class VisibleModel:
    def __init__(self):
        self.reset()

    def reset(self):
        self.step_text = ""
        self.action_text = ""
        self.running_since = None      # time.time() de la fase en curso (None = terminada)
        self.last_elapsed = None
        self.trail = deque(maxlen=TRAIL)

    # ----- barra -------------------------------------------------------------------------
    def bar_lines(self, now=None):
        """(linea de paso, linea de accion con su duracion, rastro de fases recientes)."""
        now = time.time() if now is None else now
        action = self.action_text
        if self.running_since is not None:
            action += f"  {max(0.0, now - self.running_since):.1f} s"
        elif self.last_elapsed is not None and action:
            action += f"  ({self.last_elapsed:.1f} s)"
        trail = "  ·  ".join(f"{t} {e:.1f} s" for t, e in self.trail)
        return self.step_text, action, trail

    # ----- eventos -----------------------------------------------------------------------
    def handle(self, ev):
        """Procesa un core.log.Event. Devuelve la lista de comandos de dibujo (dicts)."""
        kind = ev.kind
        if kind == "step":
            self.step_text = ev.text
            return []
        if kind == "clear":
            return [{"cmd": CLEAR}]
        if kind == "log":
            return []
        if ev.elapsed is None:
            self.action_text, self.running_since, self.last_elapsed = ev.text, ev.t, None
        else:
            self.running_since, self.last_elapsed = None, ev.elapsed
            self.trail.append((_short(ev.text), ev.elapsed))
        return self._draw(ev)

    @staticmethod
    def _draw(ev):
        if ev.kind in ("click", "drag") and ev.data.get("preview") and ev.point:
            ttl = (ev.duration or 0.5) + 0.3
            if ev.kind == "drag" and ev.point2:
                return [{"cmd": LINE, "a": ev.point, "b": ev.point2, "name": ev.name, "ttl": ttl},
                        {"cmd": MARK, "point": ev.point, "name": ev.name, "ttl": ttl},
                        {"cmd": MARK, "point": ev.point2, "name": None, "ttl": ttl}]
            return [{"cmd": MARK, "point": ev.point, "name": ev.name, "ttl": ttl}]
        if ev.kind == "verify" and ev.elapsed is None:
            rect = ev.data.get("rect")
            if not rect:
                return []
            ok = bool(ev.data.get("ok"))
            pct = int(round(100 * float(ev.data.get("confidence", 0.0))))
            return [{"cmd": RECT, "rect": rect, "ok": ok, "color": GREEN if ok else RED,
                     "text": f"{ev.name or ''} {pct}%".strip(), "ttl": (ev.duration or 0.5) + 0.3}]
        return []

    @staticmethod
    def log_line(ev):
        """Linea del log para una fase terminada (None si no hay nada que anotar)."""
        if ev.kind in ("log", "clear"):
            return None
        if ev.kind == "step":
            return f"[visible] {ev.text}"
        if ev.elapsed is None:
            return None
        return f"  [visible] {ev.text}  ({ev.elapsed:.1f} s)"


def _short(text):
    text = (text or "").split(":")[0] if text.startswith(("Escribiendo", "Tecla")) else text
    return text if len(text) <= 28 else text[:27] + "…"


class VisibleController:
    """Controles del Modo visible -> core.visual.state. Nada de tkinter."""

    def __init__(self, state=None):
        self.state = state or visual.state
        self.model = VisibleModel()

    # ----- ajustes ---------------------------------------------------------------------
    @property
    def visible(self):
        return self.state.visible

    def set_visible(self, on):
        self.state.visible = bool(on)
        if not on:
            self.state.paused = False
            self.state.step_mode = False
            self.state.next_step.set()          # libera una espera de "Siguiente"
            self.state.next_step.clear()
            self.model.reset()
        return self.state.visible

    def set_speed(self, name_or_factor):
        self.state.set_speed(name_or_factor)
        return self.state.speed

    def speed_name(self):
        for n, f in SPEEDS.items():
            if abs(f - self.state.speed) < 1e-9:
                return n
        return "Normal"

    def set_speed_index(self, i):
        return self.set_speed(SPEED_NAMES[max(0, min(len(SPEED_NAMES) - 1, int(round(float(i)))))])

    def set_move_duration(self, seconds):
        self.state.configure(move_duration=float(seconds))
        return self.state.move_duration

    def set_step_mode(self, on):
        self.state.step_mode = bool(on)
        if not on:
            self.state.next_step.set()          # no dejar la accion esperando
            self.state.next_step.clear()
        return self.state.step_mode

    def toggle_pause(self):
        return self.state.toggle_pause()

    def next_step(self):
        self.state.confirm_step()

    # ----- ultima calibracion --------------------------------------------------------------
    @staticmethod
    def last_calibration():
        """Ruta de data/ultima_calibracion.png si existe, si no None."""
        import os
        path = annotate.last_calibration_path()
        return path if os.path.exists(path) else None
