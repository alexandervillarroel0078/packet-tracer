"""Barra del asistente de calibracion por demanda (cable / ip). Solo dibuja."""

import tkinter as tk
from tkinter import ttk

from panel.common import FONT_BTN

BG = "#fff3cd"


class AsistenteView(tk.Frame):
    """Aparece solo cuando una accion detecta que falta calibrar; "Continuar" calibra ese grupo."""

    def __init__(self, parent, controller, app, dry_getter):
        super().__init__(parent, bg=BG, bd=1, relief="solid")
        self.c, self.app = controller, app
        self._dry = dry_getter          # () -> bool: el Dry-run vigente de la pestana que lo uso
        self.title = tk.Label(self, text="", bg=BG, font=FONT_BTN, anchor="w")
        self.title.pack(fill="x", padx=6, pady=(4, 0))
        self.body = tk.Label(self, text="", bg=BG, justify="left", anchor="w", wraplength=380)
        self.body.pack(fill="x", padx=6, pady=2)
        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=6, pady=(2, 6))
        self.btn_go = tk.Button(row, text="Continuar", font=FONT_BTN, bg="#e65100", fg="white",
                                command=app.guard(self._continue))
        self.btn_go.pack(side="left")
        self.btn_cancel = ttk.Button(row, text="Cancelar", command=self._cancel)
        self.btn_cancel.pack(side="left", padx=6)
        app.register_action(self.btn_go)
        self.refresh()

    @property
    def visible(self):
        return bool(self.winfo_manager())

    def refresh(self):
        w = self.c.pending
        if w is None:
            self.pack_forget()
            return
        self.title.configure(text=w.title)
        self.body.configure(text=f"Faltan: {_plain(w)}.\n{w.instruction}")
        if not self.visible:
            self.pack(fill="x", padx=8, pady=(4, 0), before=self.app.nb)

    def _continue(self):
        self.c.continuar(dry_run=self._dry())

    def _cancel(self):
        self.c.dismiss()
        self.refresh()


def _plain(w):
    from core import preflight
    return preflight.plain_list(w.missing)
