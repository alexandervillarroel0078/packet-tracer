"""
panel.main - ventana principal de pt-autobuild: ensambla las 4 pestanas, el log en vivo, la
barra de estado (cuenta regresiva, progreso, DETENER) y conecta los eventos del runner.

Toda la logica esta en panel/controllers (sin tkinter); las vistas solo dibujan.
"""

import json
import os
import tkinter as tk
from tkinter import ttk

from core import log as core_log
from core import paths
from core.errors import PTError
from panel.ajustes import AjustesView
from panel.calibracion import CalibracionView
from panel.colocar import ColocarView
from panel.common import LogView, StatusBar, make_scroll_tab
from panel.configurar import ConfigurarView
from panel.controllers import Shared
from panel.controllers.ajustes import AjustesController
from panel.controllers.calibracion import CalibracionController
from panel.controllers.colocar import ColocarController
from panel.controllers.configurar import ConfigurarController
from panel.controllers.runner import ActionRunner

TABS = ("Colocar", "Configurar", "Calibracion", "Ajustes")


class PanelApp:
    def __init__(self, root, runner=None):
        self.root = root
        self.runner = runner or ActionRunner()
        self.shared = Shared(self.runner)
        self._actions = []          # widgets que se deshabilitan mientras corre algo
        self.views = {}

        root.title("pt-autobuild :: panel")
        root.attributes("-topmost", True)
        root.geometry("420x780")
        root.minsize(420, 640)
        root.resizable(True, True)
        try:
            ttk.Style().theme_use("vista")
        except tk.TclError:
            pass

        self._build_top()
        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)
        self._scroll_canvases = []

        self.status = StatusBar(root, self.runner.stop)
        self.status.pack(fill="x", padx=8, pady=2)
        self.log = LogView(root, height=8)
        self.log.pack(fill="x", padx=8, pady=4)
        ttk.Button(root, text="Limpiar log", command=self.log.clear).pack(anchor="e", padx=8)

        core_log.set_sink(self.runner.log)    # los mensajes de core/ van al log del panel

        self.controllers = {
            "Colocar": ColocarController(self.shared),
            "Configurar": ConfigurarController(self.shared),
            "Calibracion": CalibracionController(self.shared),
            "Ajustes": AjustesController(self.shared),
        }
        view_classes = {"Colocar": ColocarView, "Configurar": ConfigurarView,
                        "Calibracion": CalibracionView, "Ajustes": AjustesView}
        for name in TABS:
            inner, cv = make_scroll_tab(self.nb, name)
            self._scroll_canvases.append(cv)
            self.views[name] = view_classes[name](inner, self.controllers[name], self)

        self._restore_tab()
        self.nb.bind("<<NotebookTabChanged>>", self._save_tab)
        root.bind_all("<MouseWheel>", self._on_wheel)
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.notify("Panel listo. Dry-run MARCADO por defecto: nada se mueve hasta que lo "
                    "desmarques.")
        self.notify("Failsafe: mouse a la esquina superior izquierda = abortar. "
                    "DETENER corta la cuenta regresiva y la accion.")
        self.root.after(80, self._poll)

    # ----- barra superior --------------------------------------------------------------------
    def _build_top(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=4)
        self.topmost_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Siempre encima", variable=self.topmost_var,
                        command=lambda: self.root.attributes("-topmost", self.topmost_var.get())
                        ).pack(side="left")
        ttk.Label(top, text="Cuenta regresiva (s):").pack(side="left", padx=(12, 2))
        self.countdown_var = tk.StringVar(value="5")
        self.countdown_var.trace_add("write", self._on_countdown)
        ttk.Spinbox(top, from_=0, to=15, width=3, textvariable=self.countdown_var,
                    justify="center").pack(side="left")
        opa = ttk.Frame(self.root)
        opa.pack(fill="x", padx=8)
        self.opacity_label = ttk.Label(opa, text="Opacidad: 100%", width=15)
        self.opacity_label.pack(side="left")
        scale = tk.Scale(opa, from_=30, to=100, orient="horizontal", showvalue=False,
                         command=self._on_opacity)
        scale.set(100)
        scale.pack(side="left", fill="x", expand=True)

    def _on_countdown(self, *_):
        try:
            self.shared.countdown = max(0, min(15, int(self.countdown_var.get())))
        except ValueError:
            pass            # mientras se escribe

    def _on_opacity(self, value):
        pct = int(round(float(value)))
        try:
            self.root.attributes("-alpha", pct / 100.0)
        except tk.TclError:
            pass
        self.opacity_label.configure(text=f"Opacidad: {pct}%")

    # ----- API para las vistas -----------------------------------------------------------------
    def notify(self, msg):
        """Mensaje del panel en el log (hilo de la interfaz)."""
        self.log.append(msg)

    def report_error(self, exc):
        if isinstance(exc, PTError):
            self.log.append(f"[ERROR] {exc}")
        else:
            where = ActionRunner._save_traceback()
            self.log.append(f"[ERROR inesperado] {type(exc).__name__}: {exc}"
                            + (f"\n  (detalle tecnico en {where})" if where else ""))

    def guard(self, fn):
        """Envuelve el callback de un boton: los errores se muestran en el panel, sin trazas."""
        def wrapper(*a, **k):
            try:
                return fn(*a, **k)
            except Exception as e:  # noqa: BLE001
                self.report_error(e)
        return wrapper

    def register_action(self, widget):
        self._actions.append(widget)

    def _set_busy(self, busy):
        for w in self._actions:
            try:
                w.configure(state="disabled" if busy else "normal")
            except tk.TclError:
                pass

    # ----- eventos del runner --------------------------------------------------------------------
    def _poll(self):
        for ev in self.runner.drain():
            self._handle(ev)
        self.root.after(80, self._poll)

    def _handle(self, ev):
        kind = ev[0]
        if kind == "log":
            self.log.append(ev[1])
        elif kind == "state":
            _, state, label = ev
            self.status.set_state(state, label)
            self._set_busy(state != "idle")
        elif kind == "tick":
            self.status.set_tick(ev[1])
        elif kind == "progress":
            self.status.set_progress(ev[1], ev[2])
        elif kind == "done":
            _, status, label = ev
            self.status.set_progress(0, 1)
            for view in self.views.values():
                view.on_done(status, label)

    # ----- persistencia / cierre -------------------------------------------------------------------
    def _restore_tab(self):
        try:
            with open(paths.PANEL_STATE_PATH, encoding="utf-8") as f:
                idx = int(json.load(f).get("tab", 0))
            self.nb.select(min(max(idx, 0), len(TABS) - 1))
        except (OSError, ValueError, TypeError, tk.TclError):
            pass

    def _save_tab(self, _evt=None):
        try:
            os.makedirs(os.path.dirname(paths.PANEL_STATE_PATH), exist_ok=True)
            with open(paths.PANEL_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"tab": self.nb.index("current")}, f)
        except (OSError, tk.TclError):
            pass

    def _on_wheel(self, event):
        w = self.root.winfo_containing(event.x_root, event.y_root)
        while w is not None:
            if w in self._scroll_canvases:
                w.yview_scroll(int(-event.delta / 120), "units")
                return
            w = getattr(w, "master", None)

    def close(self):
        self.runner.stop()
        view = self.views.get("Calibracion")
        if view is not None:
            view.close()
        core_log.set_sink(None)
        self.root.destroy()


def main():
    root = tk.Tk()
    PanelApp(root)
    root.mainloop()
