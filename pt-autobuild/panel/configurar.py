"""Vista de la pestana Configurar. Solo dibuja; la logica esta en controllers/configurar.py."""

import tkinter as tk
from tkinter import ttk

from panel.common import ModeButton, bind_mode

PAD = dict(padx=8, pady=4)


class ConfigurarView:
    def __init__(self, parent, controller, app):
        self.c, self.app = controller, app
        self.root = parent
        self.dry_var = tk.BooleanVar(value=True)           # MARCADO por defecto
        self.skip_var = tk.BooleanVar(value=False)

        # ---- dry-run comun (IP y hostname) ----------------------------------------------
        top = ttk.LabelFrame(parent, text="Seguridad")
        top.pack(fill="x", **PAD)
        ttk.Checkbutton(top, variable=self.dry_var,
                        text="Dry-run (muestra el plan; NO mueve el mouse)").pack(
            anchor="w", padx=6, pady=4)

        # ---- IP ----------------------------------------------------------------------------
        fi = ttk.LabelFrame(parent, text="IP en PCs")
        fi.pack(fill="x", **PAD)
        r = ttk.Frame(fi)
        r.pack(fill="x", padx=6, pady=4)
        ttk.Label(r, text="PC:").pack(side="left")
        self.pc_var = tk.StringVar()
        self.pc_cb = ttk.Combobox(r, textvariable=self.pc_var, width=10, state="readonly")
        self.pc_cb.pack(side="left", padx=4)
        self.pc_cb.bind("<<ComboboxSelected>>", lambda e: self._fill_ip())
        self.btn_refresh = ttk.Button(r, text="Actualizar", command=self.refresh_devices)
        self.btn_refresh.pack(side="left")
        self.ip_var, self.mask_var, self.gw_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for label, var in (("IPv4", self.ip_var), ("Mascara", self.mask_var),
                           ("Gateway", self.gw_var)):
            rr = ttk.Frame(fi)
            rr.pack(fill="x", padx=6, pady=1)
            ttk.Label(rr, text=label, width=8).pack(side="left")
            ttk.Entry(rr, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Checkbutton(fi, variable=self.skip_var,
                        text="Ventana ya abierta en IP Configuration (solo escribir)").pack(
            anchor="w", padx=6)
        self.btn_ip = ModeButton(fi, "Previsualizar IP (dry-run)",
                                 "APLICAR IP (mueve el mouse de verdad)", app.guard(self._ip))
        self.btn_ip.pack(fill="x", padx=6, pady=(4, 2))
        bind_mode(self.btn_ip, self.dry_var)
        self.btn_ip_all = ModeButton(fi, "Previsualizar IP de todas las PCs (dry-run)",
                                     "APLICAR IP A TODAS LAS PCs (mueve el mouse)",
                                     app.guard(self._ip_all))
        self.btn_ip_all.pack(fill="x", padx=6, pady=(0, 6))
        bind_mode(self.btn_ip_all, self.dry_var)

        # ---- hostname ------------------------------------------------------------------------
        fh = ttk.LabelFrame(parent, text="Hostname de routers (CLI)")
        fh.pack(fill="x", **PAD)
        r = ttk.Frame(fh)
        r.pack(fill="x", padx=6, pady=4)
        ttk.Label(r, text="Router:").pack(side="left")
        self.router_var = tk.StringVar()
        self.router_cb = ttk.Combobox(r, textvariable=self.router_var, width=10, state="readonly")
        self.router_cb.pack(side="left", padx=4)
        ttk.Label(r, text="Hostname:").pack(side="left")
        self.host_var = tk.StringVar()
        ttk.Entry(r, textvariable=self.host_var, width=10).pack(side="left", padx=4)
        self.btn_host = ModeButton(fh, "Previsualizar hostname (dry-run)",
                                   "CAMBIAR HOSTNAME (mueve el mouse de verdad)",
                                   app.guard(self._host))
        self.btn_host.pack(fill="x", padx=6, pady=(0, 6))
        bind_mode(self.btn_host, self.dry_var)

        # ---- config_gen -----------------------------------------------------------------------
        fg = ttk.LabelFrame(parent, text="Generar configuracion de routers (solo calculo)")
        fg.pack(fill="both", expand=True, **PAD)
        ttk.Label(fg, text="Usa la topologia de la pestana Colocar.").pack(
            anchor="w", padx=6, pady=(4, 0))
        r = ttk.Frame(fg)
        r.pack(fill="x", padx=6, pady=4)
        ttk.Label(r, text="Modo:").pack(side="left")
        self.mode_var = tk.StringVar(value="Estatico")
        ttk.Combobox(r, textvariable=self.mode_var, values=["Estatico", "RIP"],
                     state="readonly", width=10).pack(side="left", padx=4)
        self.btn_gen = ttk.Button(r, text="Generar", command=app.guard(self._generate))
        self.btn_gen.pack(side="left")
        self.btn_copy = ttk.Button(r, text="Copiar", command=app.guard(self._copy))
        self.btn_copy.pack(side="left", padx=4)
        wrap = ttk.Frame(fg)
        wrap.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.out = tk.Text(wrap, height=10, width=36, wrap="none", state="disabled",
                           bg="#111", fg="#d0d0d0")
        sb = ttk.Scrollbar(wrap, command=self.out.yview)
        self.out.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.out.pack(side="left", fill="both", expand=True)

        for b in (self.btn_ip, self.btn_ip_all, self.btn_host, self.btn_gen, self.btn_copy,
                  self.btn_refresh):
            app.register_action(b)
        self.refresh_devices()

    # ----- helpers ------------------------------------------------------------------------------
    def refresh_devices(self):
        pcs, routers = self.c.list_pcs(), self.c.list_routers()
        self.pc_cb.configure(values=pcs)
        self.router_cb.configure(values=routers)
        if pcs and self.pc_var.get() not in pcs:
            self.pc_var.set(pcs[0])
            self._fill_ip()
        if routers and self.router_var.get() not in routers:
            self.router_var.set(routers[0])

    def _fill_ip(self):
        ip, mask, gw = self.c.device_ip_data(self.pc_var.get())
        if ip:
            self.ip_var.set(ip)
            self.mask_var.set(mask)
            self.gw_var.set(gw)

    def _set_out(self, text):
        self.out.configure(state="normal")
        self.out.delete("1.0", "end")
        self.out.insert("1.0", text)
        self.out.configure(state="disabled")

    # ----- acciones ---------------------------------------------------------------------------------
    def _ip(self):
        self.c.apply_ip(self.pc_var.get(), self.ip_var.get().strip(), self.mask_var.get().strip(),
                        self.gw_var.get().strip(), skip_open=self.skip_var.get(),
                        dry_run=self.dry_var.get())

    def _ip_all(self):
        self.c.apply_all_ips(skip_open=self.skip_var.get(), dry_run=self.dry_var.get())

    def _host(self):
        self.c.set_hostname(self.router_var.get(), self.host_var.get().strip(),
                            dry_run=self.dry_var.get())

    def _generate(self):
        res = self.c.generate_config(self.app.shared.topology_text(), self.mode_var.get())
        self._set_out(res.text())
        self.app.notify(f"[Config] modo {self.mode_var.get()}: {len(res.configs)} router(es), "
                        f"{len(res.warnings)} aviso(s).")

    def _copy(self):
        text = self.out.get("1.0", "end").strip()
        if not text:
            self.app.notify("[!] no hay configuracion generada que copiar.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.app.notify("Configuracion copiada al portapapeles.")

    def on_done(self, status, label):
        self.refresh_devices()
