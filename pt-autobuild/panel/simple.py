"""Vista de la pestana Simple: topologia, boton Construir, Dry-run. Solo dibuja."""

import tkinter as tk
from tkinter import ttk

from panel.common import ModeButton, bind_mode
from panel.controllers.simple import EXAMPLE_TEXT

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

        ttk.Checkbutton(parent, variable=self.dry_var,
                        text="Dry-run (solo simula: no mueve el mouse)").pack(anchor="w", **PAD)

        app.register_action(self.btn_build)

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

    def on_done(self, status, label):
        self.app.refresh_status()
