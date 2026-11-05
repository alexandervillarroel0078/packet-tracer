"""
core.visual - estado del "Modo visible" y de la velocidad (sin tkinter).

Un unico estado global (`state`) que consultan core/hands.py y quienes duermen/esperan:
    visible        ver todo el proceso: mouse con movimiento, overlay de destinos, barra de accion
    simulate       solo mostrar los destinos: NO mueve el mouse real ni hace clics
    speed          factor que escala TODAS las pausas y duraciones (Rapido 0.5, Normal 1, Lento 2)
    move_duration  s que tarda el mouse en llegar a un punto en modo visible (0.4-0.8)
    step_mode      espera confirmacion ("Siguiente") antes de cada clic
    paused         congela la accion hasta "Continuar"
Detener (cancel) sigue funcionando incluso en una pausa o en espera de confirmacion.
"""

import threading
import time

from core.errors import CancelledError

SPEEDS = {"Rápido": 0.5, "Normal": 1.0, "Lento": 2.0}
SPEED_NAMES = tuple(SPEEDS)
MOVE_MIN, MOVE_MAX = 0.4, 0.8
CLICK_PAUSE = 0.2          # pausa corta antes de cada clic en modo visible
PREVIEW = 0.5              # s que se ve el circulo/cruz antes de cada clic


class VisualState:
    def __init__(self):
        self._lock = threading.Lock()
        self.cancel = None                      # threading.Event de la accion en curso
        self.next_step = threading.Event()      # "Siguiente" (paso a paso)
        self.reset()

    def reset(self):
        self.visible = False
        self.simulate = False
        self.speed = 1.0
        self.move_duration = 0.5
        self.click_pause = CLICK_PAUSE
        self.preview = PREVIEW
        self.step_mode = False
        self.paused = False
        self.next_step.clear()

    def configure(self, **kw):
        for k, v in kw.items():
            if not hasattr(self, k) or k.startswith("_"):
                raise AttributeError(k)
            setattr(self, k, v)
        self.speed = max(0.05, float(self.speed))
        self.move_duration = min(MOVE_MAX, max(MOVE_MIN, float(self.move_duration)))

    # ----- tiempos ---------------------------------------------------------------------
    def scale(self, seconds):
        """Una pausa/duracion escalada por la velocidad elegida."""
        return max(0.0, float(seconds)) * self.speed

    def set_speed(self, name_or_factor):
        f = SPEEDS.get(name_or_factor, name_or_factor)
        self.speed = max(0.05, float(f))

    # ----- control en vivo ---------------------------------------------------------------
    def toggle_pause(self):
        self.paused = not self.paused
        return self.paused

    def confirm_step(self):
        self.next_step.set()

    def check_cancel(self):
        if self.cancel is not None and self.cancel.is_set():
            raise CancelledError("accion cancelada por el usuario")

    def wait_gate(self, step=False, poll=0.05, sleep=time.sleep):
        """
        Bloquea mientras haya pausa y, si step=True y esta el paso a paso, hasta "Siguiente".
        Lanza CancelledError si se pulsa Detener. Devuelve True si tuvo que esperar.
        """
        waited = False
        while self.paused:
            waited = True
            self.check_cancel()
            sleep(poll)
        if step and self.step_mode and self.visible:
            waited = True
            self.next_step.clear()
            while not self.next_step.is_set():
                self.check_cancel()
                sleep(poll)
                while self.paused:
                    self.check_cancel()
                    sleep(poll)
            self.next_step.clear()
        self.check_cancel()
        return waited


state = VisualState()


class simulating:
    """Context manager: simulacion visual (sin mouse real) mientras dure el bloque."""

    def __init__(self, on=True):
        self.on = bool(on)

    def __enter__(self):
        self._prev = state.simulate
        state.simulate = self.on
        return self

    def __exit__(self, *exc):
        state.simulate = self._prev
        return False
