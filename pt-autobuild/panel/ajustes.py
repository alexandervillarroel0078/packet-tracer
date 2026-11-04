"""Vista de la pestana Ajustes. Solo dibuja; la logica esta en controllers/ajustes.py."""

import tkinter as tk
from tkinter import ttk

PAD = dict(padx=8, pady=4)


class AjustesView:
    def __init__(self, parent, controller, app):
        self.c, self.app = controller, app
        saved = self.c.load()
        self.values = {p: dict(v) for p, v in saved["providers"].items()}   # clave/modelo por proveedor
        self.names = dict(self.c.providers())
        self.current = saved["provider"]

        fk = ttk.LabelFrame(parent, text="IA para autocalibrar")
        fk.pack(fill="x", **PAD)

        ttk.Label(fk, text="Proveedor:").pack(anchor="w", padx=6, pady=(4, 0))
        self.provider_var = tk.StringVar(value=self.names[self.current])
        self.provider_cb = ttk.Combobox(fk, textvariable=self.provider_var, state="readonly",
                                        values=[n for _p, n in self.c.providers()])
        self.provider_cb.pack(fill="x", padx=6)
        self.provider_cb.bind("<<ComboboxSelected>>", lambda e: self._on_provider())

        self.key_label = ttk.Label(fk, text="")
        self.key_label.pack(anchor="w", padx=6, pady=(6, 0))
        row = ttk.Frame(fk)
        row.pack(fill="x", padx=6)
        self.key_var = tk.StringVar()
        self.key_entry = ttk.Entry(row, textvariable=self.key_var, show="•")
        self.key_entry.pack(side="left", fill="x", expand=True)
        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="Mostrar", variable=self.show_var,
                        command=self._toggle_show).pack(side="left", padx=4)
        self.key_hint = ttk.Label(fk, text="", foreground="#555", wraplength=330, justify="left")
        self.key_hint.pack(anchor="w", padx=6)

        ttk.Label(fk, text="Modelo (con vision):").pack(anchor="w", padx=6, pady=(6, 0))
        self.model_var = tk.StringVar()
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
        self._load_provider(self.current)
        self.refresh_dpi()

    # ----- proveedor activo en pantalla ---------------------------------------------------
    def selected(self):
        """Clave interna ('openai'/'anthropic') del proveedor elegido en el selector."""
        shown = self.provider_var.get()
        return next((p for p, n in self.names.items() if n == shown), self.current)

    def _remember(self):
        """Guarda lo escrito para el proveedor mostrado, antes de cambiar de proveedor."""
        self.values[self.current] = {"api_key": self.key_var.get(),
                                     "model": self.model_var.get(), "has_key": False}

    def _load_provider(self, provider):
        self.current = provider
        v = self.values.get(provider, {})
        self.key_var.set(v.get("api_key", ""))
        self.model_var.set(v.get("model", ""))
        var, url = self.c.key_help(provider)
        self.key_label.configure(text=f"API key de {self.names[provider]} ({var}):")
        self.key_hint.configure(text=f"Obtenla en {url}")

    def _on_provider(self):
        self._remember()
        self._load_provider(self.selected())

    def _toggle_show(self):
        self.key_entry.configure(show="" if self.show_var.get() else "•")

    # ----- acciones -------------------------------------------------------------------------
    def _save(self):
        self.app.notify(self.c.save(self.key_var.get(), self.model_var.get(), self.selected()))
        self.app.refresh_status()

    def _test(self):
        self.c.test_connection(self.key_var.get(), self.model_var.get(), self.selected())

    def refresh_dpi(self):
        ok, lines = self.c.dpi_report()
        self.dpi_out.configure(state="normal")
        self.dpi_out.delete("1.0", "end")
        self.dpi_out.insert("1.0", ("OK\n" if ok else "ATENCION\n") + "\n".join(lines))
        self.dpi_out.configure(state="disabled")

    def on_done(self, status, label):
        pass
