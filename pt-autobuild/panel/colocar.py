"""Vista de la pestana Colocar/Construir. Solo dibuja; la logica esta en controllers/colocar.py."""

import tkinter as tk
from tkinter import filedialog, ttk

from panel.common import ModeButton, bind_mode

PAD = dict(padx=8, pady=4)


class ColocarView:
    def __init__(self, parent, controller, app):
        self.c, self.app = controller, app
        self.dry_var = tk.BooleanVar(value=True)           # MARCADO por defecto
        self.random_var = tk.BooleanVar(value=False)

        # ---- topologia --------------------------------------------------------------
        f = ttk.LabelFrame(parent, text="Topologia")
        f.pack(fill="both", expand=True, **PAD)
        ttk.Label(f, text='Ej: "2 routers, 2 switches, 4 PC"  o sintaxis por redes').pack(
            anchor="w", padx=6, pady=(4, 0))
        self.text = tk.Text(f, height=8, width=36, wrap="word")
        self.text.pack(fill="both", expand=True, padx=6, pady=4)

        row = ttk.Frame(f)
        row.pack(fill="x", padx=6)
        self.example_var = tk.StringVar()
        self.example_cb = ttk.Combobox(row, textvariable=self.example_var, state="readonly",
                                       width=14, values=self.c.list_examples())
        self.example_cb.pack(side="left")
        self.btn_example = ttk.Button(row, text="Cargar ejemplo", command=app.guard(self._example))
        self.btn_example.pack(side="left", padx=4)
        self.btn_file = ttk.Button(row, text="Cargar archivo...", command=app.guard(self._file))
        self.btn_file.pack(side="left")

        # ---- vista previa y preflight -----------------------------------------------
        fp = ttk.LabelFrame(parent, text="Plan y calibracion")
        fp.pack(fill="both", expand=True, **PAD)
        row2 = ttk.Frame(fp)
        row2.pack(fill="x", padx=6, pady=4)
        self.btn_preview = ttk.Button(row2, text="Vista previa del plan",
                                      command=app.guard(self._preview))
        self.btn_preview.pack(side="left")
        self.btn_pre = ttk.Button(row2, text="Comprobar calibracion",
                                  command=app.guard(self._preflight))
        self.btn_pre.pack(side="left", padx=4)
        self.out = tk.Text(fp, height=8, width=36, wrap="none", state="disabled",
                           bg="#111", fg="#d0d0d0")
        self.out.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self.pre_label = ttk.Label(fp, text="", wraplength=330, justify="left")
        self.pre_label.pack(fill="x", padx=6)
        self.btn_recal = tk.Button(fp, text="Recalibrar y continuar", state="disabled",
                                   command=app.guard(self._recalibrate), font=("Segoe UI", 9, "bold"))
        self.btn_recal.pack(fill="x", padx=6, pady=(2, 6))

        # ---- construir -----------------------------------------------------------------
        fb = ttk.LabelFrame(parent, text="Construir")
        fb.pack(fill="x", **PAD)
        ttk.Checkbutton(fb, variable=self.dry_var,
                        text="Dry-run (solo calcula y muestra el plan; NO mueve el mouse)"
                        ).pack(anchor="w", padx=6, pady=(4, 2))
        self.btn_build = ModeButton(fb, "Previsualizar construccion (dry-run)",
                                    "CONSTRUIR (mueve el mouse de verdad)",
                                    app.guard(self._build))
        self.btn_build.pack(fill="x", padx=6, pady=(0, 6))
        bind_mode(self.btn_build, self.dry_var)

        # ---- mover dispositivo -------------------------------------------------------------
        fm = ttk.LabelFrame(parent, text="Mover dispositivo")
        fm.pack(fill="x", **PAD)
        r = ttk.Frame(fm)
        r.pack(fill="x", padx=6, pady=4)
        self.dev_var = tk.StringVar()
        self.dev_cb = ttk.Combobox(r, textvariable=self.dev_var, width=10, state="readonly")
        self.dev_cb.pack(side="left")
        ttk.Label(r, text=" X").pack(side="left")
        self.x_var, self.y_var = tk.StringVar(), tk.StringVar()
        ttk.Entry(r, textvariable=self.x_var, width=6).pack(side="left", padx=2)
        ttk.Label(r, text="Y").pack(side="left")
        ttk.Entry(r, textvariable=self.y_var, width=6).pack(side="left", padx=2)
        ttk.Checkbutton(fm, text="posicion aleatoria", variable=self.random_var).pack(
            anchor="w", padx=6)
        ttk.Label(fm, text="(usa el mismo Dry-run de arriba)").pack(anchor="w", padx=6)
        self.btn_move = ModeButton(fm, "Previsualizar movimiento (dry-run)",
                                   "MOVER dispositivo (mueve el mouse de verdad)",
                                   app.guard(self._move))
        self.btn_move.pack(fill="x", padx=6, pady=(2, 6))
        bind_mode(self.btn_move, self.dry_var)
        self.btn_refresh_dev = ttk.Button(fm, text="Actualizar dispositivos",
                                          command=self.refresh_devices)
        self.btn_refresh_dev.pack(anchor="e", padx=6, pady=(0, 6))
        self.refresh_devices()

        for b in (self.btn_example, self.btn_file, self.btn_preview, self.btn_pre,
                  self.btn_build, self.btn_move, self.btn_recal, self.btn_refresh_dev):
            app.register_action(b)
        app.shared.topology_getter = self.get_text

    # ----- helpers ------------------------------------------------------------------------
    def get_text(self):
        return self.text.get("1.0", "end").strip()

    def set_text(self, text):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)

    def _show(self, text):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        self.out.configure(state="disabled")

    def refresh_devices(self):
        names = self.c.list_devices()
        self.dev_cb.configure(values=names)
        if names and self.dev_var.get() not in names:
            self.dev_var.set(names[0])

    # ----- acciones ------------------------------------------------------------------------
    def _example(self):
        name = self.example_var.get()
        if not name:
            self.app.notify("[!] elige un ejemplo de la lista.")
            return
        self.set_text(self.c.load_example(name))
        self.app.notify(f"Ejemplo '{name}' cargado.")

    def _file(self):
        path = filedialog.askopenfilename(
            title="Cargar topologia", filetypes=[("Topologia (txt/json)", "*.txt *.json"),
                                                 ("Todos", "*.*")])
        if path:
            self.set_text(self.c.load_file(path))
            self.app.notify(f"Cargado: {path}")

    def _preview(self):
        res = self.c.preview(self.get_text())
        self._show(res.text() + ("" if res.ok else f"\n\nERROR: {res.error}"))
        if not res.ok:
            self.app.notify(f"[ERROR] {res.error}")

    def _preflight(self):
        self.c.start_preflight(self.get_text())

    def _build(self):
        outcome = self.c.build(self.get_text(), dry_run=self.dry_var.get())
        self._after_outcome(outcome)

    def _after_outcome(self, outcome):
        if outcome.status == "blocked":
            self._show_preflight(outcome.preflight)
            self.app.notify("[!] No se construyo: la calibracion no esta lista. "
                            "No se movio nada.")

    def _show_preflight(self, result):
        if result is None:
            return
        self.pre_label.configure(text=result.summary(),
                                 foreground="#2e7d32" if result.ok else "#c62828")
        lines = [f"{st.upper():<11} {n}" for n, st, _ in result.items]
        self._show("\n".join(lines))
        self.btn_recal.configure(state="normal" if not result.ok else "disabled",
                                 bg="#e65100" if not result.ok else "SystemButtonFace",
                                 fg="white" if not result.ok else "black")

    def _recalibrate(self):
        self.c.recalibrate_and_continue(self.get_text(), dry_run=self.dry_var.get())

    def _move(self):
        self.c.move_device(self.dev_var.get(), self.x_var.get(), self.y_var.get(),
                           random_pos=self.random_var.get(), dry_run=self.dry_var.get())

    # llamado por la ventana al terminar una accion
    def on_done(self, status, label):
        if self.c.last_preflight is not None:
            self._show_preflight(self.c.last_preflight)
        self.refresh_devices()
