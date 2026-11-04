"""
panel.controllers.runner - ejecucion de acciones largas en hilos (SIN tkinter).

ActionRunner corre una funcion en un hilo, con:
  - cuenta regresiva visible y cancelable antes de tocar el mouse (touches_mouse=True),
  - failsafe de pyautogui activo en esas acciones,
  - un threading.Event de cancelacion (boton Detener) que se pasa a la accion,
  - mensajes de log y progreso hacia la interfaz mediante una cola de eventos,
  - errores PTError como mensaje claro; cualquier otro error inesperado se resume en el log
    y la traza completa va a data/panel_errors.log (nunca a la consola).

La interfaz consulta drain() periodicamente. En pruebas, ActionRunner(sync=True) ejecuta
inline y sin hilos.
"""

import datetime
import os
import queue
import threading
import time
import traceback

from core import log as core_log
from core import paths
from core.errors import CancelledError, PTError

IDLE, COUNTDOWN, RUNNING = "idle", "countdown", "running"


class RunContext:
    """Lo que recibe la accion: log, cancel y progress."""

    def __init__(self, runner):
        self._runner = runner
        self.cancel = runner.cancel

    def log(self, msg=""):
        self._runner._put(("log", str(msg)))

    def progress(self, done, total):
        self._runner._put(("progress", int(done), int(total)))


class ActionRunner:
    def __init__(self, sync=False, tick_seconds=1.0):
        self.sync = sync
        self.tick_seconds = tick_seconds
        self.cancel = threading.Event()
        self.state = IDLE
        self.label = ""
        self.touches_mouse = False
        self._events = queue.Queue()
        self._thread = None
        self._lock = threading.Lock()

    # ----- estado -----------------------------------------------------
    @property
    def busy(self):
        return self.state != IDLE

    def _put(self, ev):
        self._events.put(ev)

    def drain(self):
        out = []
        try:
            while True:
                out.append(self._events.get_nowait())
        except queue.Empty:
            pass
        return out

    def log(self, msg=""):
        self._put(("log", str(msg)))

    # ----- control ----------------------------------------------------
    def start(self, label, fn, *, touches_mouse=False, countdown=0, on_done=None):
        """
        Lanza fn(ctx). Devuelve False (y avisa en el log) si ya hay una accion en curso.
        countdown se ignora si touches_mouse es False.
        """
        with self._lock:
            if self.busy:
                self.log("[espera] ya hay una accion en curso.")
                return False
            self.cancel.clear()
            self.label = label
            self.touches_mouse = bool(touches_mouse)
            self.state = COUNTDOWN if (touches_mouse and countdown > 0) else RUNNING
        self._put(("state", self.state, label))
        args = (label, fn, bool(touches_mouse), max(0, int(countdown)), on_done)
        if self.sync:
            self._run(*args)
        else:
            self._thread = threading.Thread(target=self._run, args=args, daemon=True)
            self._thread.start()
        return True

    def stop(self):
        """Boton Detener: cancela la cuenta regresiva o la accion en curso."""
        if self.busy:
            self.cancel.set()
            self.log("  Deteniendo...")

    def join(self, timeout=10):
        if self._thread is not None:
            self._thread.join(timeout)

    # ----- hilo -------------------------------------------------------
    def _run(self, label, fn, touches_mouse, countdown, on_done):
        ctx = RunContext(self)
        status = "ok"
        result = None
        with core_log.capture(ctx.log):
            try:
                ctx.log("")
                ctx.log("=" * 40)
                ctx.log(f"  {label}")
                ctx.log("=" * 40)
                if touches_mouse:
                    self._arm_failsafe()
                    for i in range(countdown, 0, -1):
                        if self.cancel.is_set():
                            raise CancelledError("cancelado durante la cuenta regresiva: "
                                                 "no se movio nada")
                        self._put(("tick", i))
                        ctx.log(f"  Empezando en {i}...  (enfoca Packet Tracer; "
                                "Detener o mouse a la esquina superior izquierda = abortar)")
                        if self.cancel.wait(self.tick_seconds):
                            raise CancelledError("cancelado durante la cuenta regresiva: "
                                                 "no se movio nada")
                    self._put(("tick", 0))
                self.state = RUNNING
                self._put(("state", RUNNING, label))
                result = fn(ctx)
                ctx.log(f"=== {label}: terminado ===")
            except CancelledError as e:
                status = "cancelled"
                ctx.log(f"[detenido] {e}")
            except PTError as e:
                status = "error"
                ctx.log(f"[ERROR] {e}")
            except Exception as e:  # noqa: BLE001
                if type(e).__name__ == "FailSafeException":
                    status = "cancelled"
                    ctx.log("[FAILSAFE] mouse en la esquina superior izquierda: accion abortada.")
                else:
                    status = "error"
                    where = self._save_traceback()
                    ctx.log(f"[ERROR inesperado] {type(e).__name__}: {e}")
                    if where:
                        ctx.log(f"  (detalle tecnico guardado en {where})")
            finally:
                self.state = IDLE
                self._put(("state", IDLE, label))
                self._put(("done", status, label))
                if on_done is not None:
                    try:
                        on_done(status, result)
                    except Exception:  # noqa: BLE001 - un callback de UI no debe romper el hilo
                        pass

    @staticmethod
    def _arm_failsafe():
        try:
            import pyautogui
        except ImportError as e:
            raise PTError("falta pyautogui. Instala:  pip install -r requirements.txt") from e
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.0

    @staticmethod
    def _save_traceback():
        path = os.path.join(paths.DATA_DIR, "panel_errors.log")
        try:
            os.makedirs(paths.DATA_DIR, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.datetime.now().isoformat(timespec='seconds')} ---\n")
                f.write(traceback.format_exc())
            return path
        except OSError:
            return None


def sleep_cancelable(cancel, seconds):
    """Espera `seconds` o hasta que cancel se active. True si se cancelo."""
    return cancel.wait(seconds) if cancel is not None else (time.sleep(seconds) or False)
