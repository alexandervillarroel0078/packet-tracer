"""Vista de la pestana Calibracion. Solo dibuja; la logica esta en controllers/calibracion.py."""

import tkinter as tk
from tkinter import ttk

from panel.common import COLOR_DRY, COLOR_REAL, FONT_BTN
from panel.overlay import OverlayManager

PAD = dict(padx=8, pady=4)


class CalibracionView:
    def __init__(self, parent, controller, app):
        self.c, self.app = controller, app
        self.overlays = OverlayManager(parent.winfo_toplevel(), app.notify)
        self.group_vars = {g: tk.BooleanVar(value=(g == "main")) for g in ("main", "cable", "ip")}

        # ---- grupos + instrucciones ------------------------------------------------------
        fg = ttk.LabelFrame(parent, text="Que calibrar")
        fg.pack(fill="x", **PAD)
        row = ttk.Frame(fg)
        row.pack(fill="x", padx=6, pady=4)
        for g, label in (("main", "main"), ("cable", "cable"), ("ip", "ip")):
            ttk.Checkbutton(row, text=label, variable=self.group_vars[g],
                            command=self._refresh_instructions).pack(side="left", padx=4)
        self.instr = tk.Label(fg, text="", justify="left", anchor="w", wraplength=340,
                              bg="#fff8e1", fg="#333", relief="solid", bd=1)
        self.instr.pack(fill="x", padx=6, pady=(0, 6))

        # ---- IA ---------------------------------------------------------------------------------
        fa = ttk.LabelFrame(parent, text="Autocalibracion con IA")
        fa.pack(fill="x", **PAD)
        self.btn_auto = tk.Button(fa, text="Autocalibrar (guarda y escribe en el buscador)",
                                  bg=COLOR_REAL, fg="white", font=FONT_BTN,
                                  command=app.guard(self._auto))
        self.btn_auto.pack(fill="x", padx=6, pady=(4, 2))
        self.btn_show = tk.Button(fa, text="Solo mostrar (dry-run, no guarda)", bg=COLOR_DRY,
                                  fg="white", font=FONT_BTN, command=app.guard(self._show))
        self.btn_show.pack(fill="x", padx=6, pady=2)
        self.btn_force = tk.Button(fa, text="Forzar (ignora la cache; escribe en el buscador)",
                                   bg=COLOR_REAL, fg="white", font=FONT_BTN,
                                   command=app.guard(self._force))
        self.btn_force.pack(fill="x", padx=6, pady=2)
        self.btn_verify = tk.Button(fa, text="Verificar (sin API, solo mira la pantalla)",
                                    bg=COLOR_DRY, fg="white", font=FONT_BTN,
                                    command=app.guard(self._verify))
        self.btn_verify.pack(fill="x", padx=6, pady=(2, 6))

        # ---- tabla de estado -------------------------------------------------------------------
        ft = ttk.LabelFrame(parent, text="Estado por elemento")
        ft.pack(fill="x", **PAD)
        self.tree = ttk.Treeview(ft, columns=("archivo", "estado"), height=9)
        self.tree.heading("#0", text="Elemento")
        self.tree.heading("archivo", text="Archivo")
        self.tree.heading("estado", text="Estado")
        self.tree.column("#0", width=150, stretch=True)
        self.tree.column("archivo", width=50, stretch=False)
        self.tree.column("estado", width=100, stretch=False)
        self.tree.tag_configure("ok", foreground="#1a8f2e")
        self.tree.tag_configure("manual", foreground="#c62828")
        self.tree.tag_configure("unverified", foreground="#b8860b")
        self.tree.pack(fill="x", padx=6, pady=(6, 2))
        self.btn_status = ttk.Button(ft, text="Actualizar estado", command=self.refresh_status)
        self.btn_status.pack(fill="x", padx=6, pady=(0, 6))

        # ---- captura manual (F8) -----------------------------------------------------------------
        fm = ttk.LabelFrame(parent, text="Captura manual (mueve el mouse y pulsa F8)")
        fm.pack(fill="x", **PAD)
        r = ttk.Frame(fm)
        r.pack(fill="x", padx=6, pady=4)
        self.point_var = tk.StringVar()
        ttk.Combobox(r, textvariable=self.point_var, values=self.c.manual_points(),
                     state="readonly", width=20).pack(side="left")
        self.btn_cap = ttk.Button(r, text="Capturar punto", command=app.guard(self._capture))
        self.btn_cap.pack(side="left", padx=4)
        self.btn_ip = ttk.Button(fm, text="Calibrar ventana IP", command=app.guard(self._ip))
        self.btn_ip.pack(fill="x", padx=6, pady=1)
        self.btn_router = ttk.Button(fm, text="Calibrar router (CLI)",
                                     command=app.guard(self._router))
        self.btn_router.pack(fill="x", padx=6, pady=1)
        r2 = ttk.Frame(fm)
        r2.pack(fill="x", padx=6, pady=1)
        ttk.Label(r2, text="Cable:").pack(side="left")
        self.tipo_var = tk.StringVar(value="serial")
        ttk.Entry(r2, textvariable=self.tipo_var, width=8).pack(side="left", padx=2)
        ttk.Label(r2, text="ref:").pack(side="left")
        self.ref_var = tk.StringVar()
        self.ref_cb = ttk.Combobox(r2, textvariable=self.ref_var, width=8, state="readonly",
                                   values=self.c.list_devices())
        self.ref_cb.pack(side="left", padx=2)
        self.btn_cable = ttk.Button(r2, text="Calibrar", command=app.guard(self._cable))
        self.btn_cable.pack(side="left", padx=2)
        self.btn_img = ttk.Button(fm, text="Calibrar por imagenes de referencia",
                                  command=app.guard(self._images))
        self.btn_img.pack(fill="x", padx=6, pady=(1, 6))

        # ---- overlays -------------------------------------------------------------------------------
        fo = ttk.LabelFrame(parent, text="Overlays")
        fo.pack(fill="x", **PAD)
        self.btn_ov_cal = ttk.Button(fo, text="Mostrar overlay de calibracion",
                                     command=app.guard(self._ov_cal))
        self.btn_ov_cal.pack(fill="x", padx=6, pady=(4, 2))
        self.btn_ov_topo = ttk.Button(fo, text="Mostrar overlay de topologia",
                                      command=app.guard(self._ov_topo))
        self.btn_ov_topo.pack(fill="x", padx=6, pady=(0, 6))

        # botones que NO actuan sobre el mouse tambien se bloquean mientras corre algo
        for b in (self.btn_auto, self.btn_show, self.btn_force, self.btn_verify, self.btn_cap,
                  self.btn_ip, self.btn_router, self.btn_cable, self.btn_img):
            app.register_action(b)
        self._refresh_instructions()
        self.refresh_status()

    # ----- helpers -----------------------------------------------------------------------------------
    def groups(self):
        return [g for g, v in self.group_vars.items() if v.get()]

    def _refresh_instructions(self):
        self.instr.configure(text=self.c.instructions(self.groups()))

    def refresh_status(self):
        rows = self.c.status_rows()
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            self.tree.insert("", "end", text=r["name"], values=(r["file"], r["label"]),
                             tags=(r["status"],))
        counts = self.c.status_counts(rows)
        self.app.notify(f"[calibracion] OK={counts['ok']}  requiere manual={counts['manual']}  "
                        f"sin verificar={counts['unverified']}")

    # ----- acciones -------------------------------------------------------------------------------------
    def _auto(self):
        self.c.autocalibrate(self.groups(), dry_run=False)

    def _show(self):
        self.c.show_only(self.groups())

    def _force(self):
        self.c.force(self.groups(), dry_run=False)

    def _verify(self):
        self.c.verify(self.groups())

    def _capture(self):
        self.c.capture_point(self.point_var.get())

    def _ip(self):
        self.c.capture_ip_window()

    def _router(self):
        self.c.capture_router()

    def _cable(self):
        self.c.capture_cable(self.tipo_var.get(), self.ref_var.get())

    def _images(self):
        self.c.calibrate_images()

    def _ov_cal(self):
        self.overlays.toggle_calibration(self.c.overlay_calibration(), self.btn_ov_cal,
                                         self.btn_ov_topo)

    def _ov_topo(self):
        self.overlays.toggle_topology(self.c.overlay_topology(), self.btn_ov_cal,
                                      self.btn_ov_topo)

    def on_done(self, status, label):
        self.ref_cb.configure(values=self.c.list_devices())
        self.refresh_status()

    def close(self):
        self.overlays.close()
