"""Vista de la pestana Ajustes. Solo dibuja; la logica esta en controllers/ajustes.py."""

import tkinter as tk
from tkinter import ttk

PAD = dict(padx=8, pady=4)


class AjustesView:
    def __init__(self, parent, controller, app):
        self.c, self.app = controller, app
        saved = self.c.load()

        fk = ttk.LabelFrame(parent, text="Autocalibracion con IA (API de Anthropic)")
        fk.pack(fill="x", **PAD)
        ttk.Label(fk, text="API key:").pack(anchor="w", padx=6, pady=(4, 0))
        row = ttk.Frame(fk)
        row.pack(fill="x", padx=6)
        self.key_var = tk.StringVar(value=saved["api_key"])
        self.key_entry = ttk.Entry(row, textvariable=self.key_var, show="•")
        self.key_entry.pack(side="left", fill="x", expand=True)
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Mostrar", variable=self.show_var,
                        command=self._toggle_show).pack(side="left", padx=4)
        ttk.Label(fk, text="Modelo:").pack(anchor="w", padx=6, pady=(4, 0))
        self.model_var = tk.StringVar(value=saved["model"])
        ttk.Entry(fk, textvariable=self.model_var).pack(fill="x", padx=6)
        ttk.Label(fk, text="Se guarda en .env (sin imprimir la clave en el log).",
                  foreground="#555").pack(anchor="w", padx=6, pady=(2, 0))
        r = ttk.Frame(fk)
        r.pack(fill="x", padx=6, pady=6)
        self.btn_save = ttk.Button(r, text="Guardar", command=app.guard(self._save))
        self.btn_save.pack(side="left")
        self.btn_test = ttk.Button(r, text="Probar conexion", command=app.guard(self._test))
        self.btn_test.pack(side="left", padx=6)

        fd = ttk.LabelFrame(parent, text="Pantalla y escala (DPI)")
        fd.pack(fill="both", expand=True, **PAD)
        self.dpi_out = tk.Text(fd, height=7, width=36, wrap="word", state="disabled",
                               bg="#111", fg="#d0d0d0")
        self.dpi_out.pack(fill="both", expand=True, padx=6, pady=(6, 2))
        self.btn_dpi = ttk.Button(fd, text="Actualizar informe", command=self.refresh_dpi)
        self.btn_dpi.pack(fill="x", padx=6, pady=(0, 6))

        app.register_action(self.btn_test)
        self.refresh_dpi()

    def _toggle_show(self):
        self.key_entry.configure(show="" if self.show_var.get() else "•")

    def _save(self):
        self.app.notify(self.c.save(self.key_var.get(), self.model_var.get()))

    def _test(self):
        self.c.test_connection(self.key_var.get(), self.model_var.get())

    def refresh_dpi(self):
        ok, lines = self.c.dpi_report()
        self.dpi_out.configure(state="normal")
        self.dpi_out.delete("1.0", "end")
        self.dpi_out.insert("1.0", ("OK\n" if ok else "ATENCION\n") + "\n".join(lines))
        self.dpi_out.configure(state="disabled")

    def on_done(self, status, label):
        pass
