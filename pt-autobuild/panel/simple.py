"""Vista de la pestana Simple: topologia, boton Construir, Dry-run. Solo dibuja."""

import tkinter as tk
from tkinter import ttk

from panel.common import ModeButton, bind_mode
from core.visual import MOVE_MAX, MOVE_MIN, SPEED_NAMES
from panel.controllers.simple import EXAMPLE_TEXT
from panel.visible_view import show_image_window

PAD = dict(padx=8, pady=4)
GRAY = "#8a8a8a"


class SimpleView:
    def __init__(self, parent, controller, app):
        self.c, self.app = controller, app
        self.dry_var = tk.BooleanVar(value=True)            # MARCADO por defecto
        self._placeholder_on = False

        f = ttk.LabelFrame(parent, text="¿Qué quieres construir?")
        f.pack(fill="both", expand=True, **PAD)
        self.text = tk.Text(f, height=7, width=36, wrap="word")
        self.text.pack(fill="both", expand=True, padx=6, pady=6)
        self.text.tag_configure("placeholder", foreground=GRAY)
        self.text.bind("<FocusIn>", self._hide_placeholder)
        self.text.bind("<FocusOut>", lambda e: self._show_placeholder())
        self._show_placeholder()

        self.btn_build = ModeButton(parent, "Construir", "Construir (mueve el mouse)",
                                    app.guard(self._build), height=2, font=("Segoe UI", 13, "bold"))
        self.btn_build.pack(fill="x", **PAD)
        bind_mode(self.btn_build, self.dry_var)

        self.btn_cal = ModeButton(parent, "Calibrar", "Calibrar (mueve el mouse)",
                                  app.guard(self._calibrate))
        self.btn_cal.pack(fill="x", **PAD)
        bind_mode(self.btn_cal, self.dry_var)

        ttk.Checkbutton(parent, variable=self.dry_var,
                        text="Dry-run (solo simula: no mueve el mouse)").pack(anchor="w", **PAD)

        ttk.Button(parent, text="Ver última calibración",
                   command=app.guard(self._view_last)).pack(fill="x", **PAD)

        self._build_visible_box(parent)
        app.register_action(self.btn_build)
        app.register_action(self.btn_cal)

    # ----- Modo visible --------------------------------------------------------------------
    def _build_visible_box(self, parent):
        vc = self.app.shared.visual
        self.visible_var = tk.BooleanVar(value=False)        # DESMARCADO por defecto
        box = ttk.LabelFrame(parent, text="Modo visible")
        box.pack(fill="x", **PAD)
        ttk.Checkbutton(box, variable=self.visible_var, command=self._on_visible,
                        text="Ver todo el proceso en vivo (barra, mouse y destinos)"
                        ).pack(anchor="w", padx=6, pady=(4, 0))

        speed = ttk.Frame(box)
        speed.pack(fill="x", padx=6, pady=2)
        ttk.Label(speed, text="Velocidad:").pack(side="left")
        self.speed_label = ttk.Label(speed, text=vc.speed_name(), width=8)
        scale = tk.Scale(speed, from_=0, to=len(SPEED_NAMES) - 1, orient="horizontal",
                         showvalue=False, length=140, command=self._on_speed)
        scale.set(SPEED_NAMES.index(vc.speed_name()))
        scale.pack(side="left", padx=4)
        self.speed_label.pack(side="left")

        mv = ttk.Frame(box)
        mv.pack(fill="x", padx=6, pady=2)
        ttk.Label(mv, text="Duración del mouse (s):").pack(side="left")
        self.move_var = tk.StringVar(value=str(vc.state.move_duration))
        self.move_var.trace_add("write", self._on_move)
        ttk.Spinbox(mv, from_=MOVE_MIN, to=MOVE_MAX, increment=0.1, width=5,
                    textvariable=self.move_var, justify="center").pack(side="left", padx=4)

        row = ttk.Frame(box)
        row.pack(fill="x", padx=6, pady=(2, 6))
        self.pause_btn = ttk.Button(row, text="Pausa", command=self._toggle_pause)
        self.pause_btn.pack(side="left")
        self.step_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Paso a paso", variable=self.step_var,
                        command=self._on_step_mode).pack(side="left", padx=8)
        self.next_btn = ttk.Button(row, text="Siguiente ▶", command=vc.next_step)
        self.next_btn.pack(side="left")
        ttk.Label(box, foreground=GRAY, wraplength=360,
                  text="Con Dry-run marcado, el modo visible solo muestra los destinos: "
                       "no mueve el mouse real ni hace clics.").pack(anchor="w", padx=6)

    def _on_visible(self):
        self.app.set_visible(self.visible_var.get())
        if not self.visible_var.get():
            self.pause_btn.configure(text="Pausa")
            self.step_var.set(False)

    def _on_speed(self, value):
        vc = self.app.shared.visual
        vc.set_speed_index(value)
        self.speed_label.configure(text=vc.speed_name())

    def _on_move(self, *_):
        try:
            self.app.shared.visual.set_move_duration(float(self.move_var.get()))
        except ValueError:
            pass               # mientras se escribe

    def _toggle_pause(self):
        paused = self.app.shared.visual.toggle_pause()
        self.pause_btn.configure(text="Continuar" if paused else "Pausa")

    def _on_step_mode(self):
        self.app.shared.visual.set_step_mode(self.step_var.get())

    def _view_last(self):
        path = self.app.shared.calibrator.last_calibration_path()
        if not path:
            self.app.notify("Aún no hay una calibración con IA: pulsa Calibrar primero.")
            return
        show_image_window(self.app.root, path)

    # ----- texto con ejemplo en gris --------------------------------------------------------
    def _show_placeholder(self):
        if not self.text.get("1.0", "end").strip():
            self.text.delete("1.0", "end")
            self.text.insert("1.0", EXAMPLE_TEXT, "placeholder")
            self._placeholder_on = True

    def _hide_placeholder(self, _evt=None):
        if self._placeholder_on:
            self.text.delete("1.0", "end")
            self._placeholder_on = False

    def get_text(self):
        return "" if self._placeholder_on else self.text.get("1.0", "end").strip()

    def set_text(self, text):
        self._hide_placeholder()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self._show_placeholder()

    # ----- acciones --------------------------------------------------------------------------
    def _build(self):
        self.c.build(self.get_text(), dry_run=self.dry_var.get())

    def _calibrate(self):
        self.c.calibrate(dry_run=self.dry_var.get())

    def on_done(self, status, label):
        self.pause_btn.configure(text="Pausa")
        self.app.refresh_status()
