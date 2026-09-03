"""
panel_control.py - Panel de control flotante para pt-autobuild.

Ventana pequena "siempre encima" con botones que disparan los MISMOS scripts
que ya usas por terminal:

    Colocar topologia   ->  build.py
    Configurar IP de PC ->  configure_ip.py
    Configurar Router   ->  routers/configure_router.py

No reimplementa nada: cada boton arma los argumentos y llama a la funcion
main() del script correspondiente. La salida (lo que verias en la terminal)
se redirige en vivo al area de log de la ventana.

Seguridad (identica a los scripts):
    - Cuenta regresiva configurable antes de cada accion (el panel la hace y
      pasa --countdown 0 al script para no duplicarla).
    - Failsafe de pyautogui SIEMPRE activo: lleva el mouse a la esquina
      superior izquierda de la pantalla para abortar la accion en curso.

Uso:
    cd pt-autobuild
    python panel_control.py

Dependencias: las de siempre (pip install -r requirements.txt). tkinter viene
incluido con Python en Windows, no hay que instalar nada extra.
"""

import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout

import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# DEBE importarse antes que pyautogui (fija DPI awareness en Windows).
from core import dpi_aware  # noqa: E402


# --------------------------------------------------------------------------
# Utilidades de validacion ligera (para no arrancar un hilo si el dato es malo;
# el script vuelve a validar de todos modos).
# --------------------------------------------------------------------------
def _looks_ipish(s):
    parts = s.split(".")
    return len(parts) == 4 and all(
        p.isdigit() and 0 <= int(p) <= 255 for p in parts
    )


_HOSTNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")


def _looks_hostname(s):
    return bool(_HOSTNAME_RE.match(s)) and not s.endswith("-")


def _is_int(s):
    try:
        int(s)
        return True
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Overlay de calibracion: recorre un dict de coordenadas (el que devuelve
# core.coords.load_coords) y saca (nombre, x, y) de cada punto [x, y].
# Entra recursivamente en sub-dicts (p. ej. coords.json -> "canvas"), ignora
# "screen_size" y valores que no son un par numerico (como "skip").
# --------------------------------------------------------------------------
def _iter_points(obj, prefix=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "screen_size":
                continue
            name = k if not prefix else f"{prefix}.{k}"
            out.extend(_iter_points(v, name))
    elif (isinstance(obj, (list, tuple)) and len(obj) == 2
          and all(isinstance(n, (int, float)) and not isinstance(n, bool)
                  for n in obj)):
        out.append((prefix, int(round(obj[0])), int(round(obj[1]))))
    return out


def _otext(cv, x, y, text, color, anchor="w"):
    """Texto con sombra negra de 1px para que se lea sobre cualquier fondo."""
    cv.create_text(x + 1, y + 1, text=text, fill="#000000", anchor=anchor,
                   font=("Segoe UI", 9, "bold"))
    cv.create_text(x, y, text=text, fill=color, anchor=anchor,
                   font=("Segoe UI", 9, "bold"))


def _draw_marker(cv, x, y, name, color):
    """Una X (contorno negro + color) en (x, y) y su etiqueta al lado."""
    r = 7
    cv.create_line(x - r, y - r, x + r, y + r, fill="#000000", width=4)
    cv.create_line(x - r, y + r, x + r, y - r, fill="#000000", width=4)
    cv.create_line(x - r, y - r, x + r, y + r, fill=color, width=2)
    cv.create_line(x - r, y + r, x + r, y - r, fill=color, width=2)
    _otext(cv, x + r + 3, y, name, color, anchor="w")


# --------------------------------------------------------------------------
# Escritor que vuelca stdout/stderr del script a una cola; el hilo de la GUI
# la drena periodicamente y lo pinta en el widget de texto.
# --------------------------------------------------------------------------
class _QueueWriter:
    def __init__(self, q):
        self._q = q

    def write(self, s):
        if s:
            self._q.put(s)

    def flush(self):  # requerido por algunas rutas de print/argparse
        pass


class PanelControl:
    REQ_IP_COORDS = [
        "desktop_tab", "ip_configuration_item", "static_radio", "close_button",
        "ipv4_address", "subnet_mask", "default_gateway",
    ]

    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.writer = _QueueWriter(self.q)
        self.running = False
        self._cancel = threading.Event()
        self._mods = None
        self._job_buttons = []
        self.overlay = None       # Toplevel del overlay activo (o None)
        self.overlay_kind = None  # "cal" | "topo" | None

        root.title("pt-autobuild :: panel")
        root.attributes("-topmost", True)
        root.resizable(False, False)
        try:
            root.minsize(330, 560)
        except tk.TclError:
            pass

        self._build_ui()
        self._emit("Panel listo. Enfoca Packet Tracer antes de cada accion.")
        self._emit("Failsafe: mouse a la esquina superior izquierda = abortar.")
        self.root.after(80, self._poll_queue)

    # ----- construccion de la interfaz ---------------------------------
    def _build_ui(self):
        pad = dict(padx=8, pady=4)
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        # Barra superior: always-on-top + cuenta regresiva
        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        self.topmost_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Siempre encima", variable=self.topmost_var,
                        command=self._toggle_topmost).pack(side="left")

        ttk.Label(top, text="Cuenta regresiva:").pack(side="left", padx=(12, 2))
        self.countdown_var = tk.StringVar(value="5")
        ttk.Spinbox(top, from_=0, to=15, width=3, textvariable=self.countdown_var,
                    justify="center").pack(side="left")

        # Control de opacidad (estilo widget de Rendimiento de la Game Bar).
        opa = ttk.Frame(self.root)
        opa.pack(fill="x", **pad)
        self.opacity_label = ttk.Label(opa, text="Opacidad: 100%", width=15)
        self.opacity_label.pack(side="left")
        self.opacity_scale = tk.Scale(opa, from_=30, to=100, orient="horizontal",
                                      showvalue=False, command=self._on_opacity)
        self.opacity_scale.set(100)  # arranca 100% opaco
        self.opacity_scale.pack(side="left", fill="x", expand=True)

        # --- Seccion: Colocar topologia ---------------------------------
        f1 = ttk.LabelFrame(self.root, text="Colocar topologia (build.py)")
        f1.pack(fill="x", **pad)
        ttk.Label(f1, text='Ej: "2 routers, 2 switches, 4 PC"').pack(
            anchor="w", padx=6, pady=(4, 0))
        self.topo_text = tk.Text(f1, height=3, width=36, wrap="word")
        self.topo_text.pack(fill="x", padx=6, pady=4)
        b1 = ttk.Button(f1, text="Colocar", command=self._on_colocar)
        b1.pack(anchor="e", padx=6, pady=(0, 6))
        self._job_buttons.append(b1)

        # --- Seccion: Configurar IP de PC -----------------------------
        f2 = ttk.LabelFrame(self.root, text="Configurar IP de PC (configure_ip.py)")
        f2.pack(fill="x", **pad)
        self.ip_name = self._labeled_entry(f2, "Dispositivo (ej. PC0)")
        self.ip_addr = self._labeled_entry(f2, "IP (ej. 192.168.10.10)")
        self.ip_mask = self._labeled_entry(f2, "Mascara (ej. 255.255.255.0)")
        self.ip_gw = self._labeled_entry(f2, "Gateway (ej. 192.168.10.1)")
        b2 = ttk.Button(f2, text="Aplicar", command=self._on_ip)
        b2.pack(anchor="e", padx=6, pady=(2, 6))
        self._job_buttons.append(b2)

        # --- Seccion: Configurar Router ------------------------------
        f3 = ttk.LabelFrame(self.root,
                            text="Configurar Router (routers/configure_router.py)")
        f3.pack(fill="x", **pad)
        self.rt_name = self._labeled_entry(f3, "Dispositivo (ej. Router0)")
        self.rt_host = self._labeled_entry(f3, "Nuevo hostname (ej. R01)")
        b3 = ttk.Button(f3, text="Aplicar", command=self._on_router)
        b3.pack(anchor="e", padx=6, pady=(2, 6))
        self._job_buttons.append(b3)

        # --- Seccion: Mover dispositivo ------------------------------
        f6 = ttk.LabelFrame(self.root, text="Mover dispositivo (move_device.py)")
        f6.pack(fill="x", **pad)
        self.mv_name = self._labeled_entry(f6, "Dispositivo (ej. Router0)")
        self.mv_x = self._labeled_entry(f6, "Nueva X (px)")
        self.mv_y = self._labeled_entry(f6, "Nueva Y (px)")
        self.mv_random = tk.BooleanVar(value=False)
        ttk.Checkbutton(f6, text="Aleatorio dentro del lienzo (ignora X / Y)",
                        variable=self.mv_random).pack(anchor="w", padx=6, pady=2)
        b6 = ttk.Button(f6, text="Mover", command=self._on_move)
        b6.pack(anchor="e", padx=6, pady=(2, 6))
        self._job_buttons.append(b6)

        # --- Seccion: Calibracion ----------------------------------------
        # Solo ATAJOS: lanzan los comandos existentes tal cual en una consola
        # NUEVA (la calibracion necesita teclado en una terminal real). No se
        # toca ni se copia nada de calibrate.py / configure_ip.py / configure_router.py.
        f5 = ttk.LabelFrame(self.root, text="Calibracion (abre una consola aparte)")
        f5.pack(fill="x", **pad)
        for text, args in (
            ("Calibrar buscador / lienzo", ["calibrate.py"]),
            ("Calibrar esquina superior-izquierda del lienzo",
             ["calibrate.py", "--manual", "canvas_top_left"]),
            ("Calibrar esquina inferior-derecha del lienzo",
             ["calibrate.py", "--manual", "canvas_bottom_right"]),
            ("Calibrar ventana IP", ["configure_ip.py", "--calibrate"]),
            ("Calibrar router (CLI)",
             [os.path.join("routers", "configure_router.py"), "--calibrate"]),
        ):
            bc = ttk.Button(f5, text=text,
                            command=lambda a=args: self._launch_console(a))
            bc.pack(fill="x", padx=6, pady=2)
            self._job_buttons.append(bc)

        ttk.Separator(f5, orient="horizontal").pack(fill="x", padx=6, pady=(6, 2))
        self.cal_overlay_btn = ttk.Button(
            f5, text="Mostrar overlay de calibracion",
            command=self._toggle_calibration_overlay)
        self.cal_overlay_btn.pack(fill="x", padx=6, pady=(0, 2))
        self.topo_overlay_btn = ttk.Button(
            f5, text="Mostrar overlay de topologia",
            command=self._toggle_topology_overlay)
        self.topo_overlay_btn.pack(fill="x", padx=6, pady=(0, 4))

        # --- Log --------------------------------------------------------
        f4 = ttk.LabelFrame(self.root, text="Log")
        f4.pack(fill="both", expand=True, **pad)
        logwrap = ttk.Frame(f4)
        logwrap.pack(fill="both", expand=True, padx=6, pady=6)
        self.log = tk.Text(logwrap, height=12, width=42, wrap="word",
                           state="disabled", bg="#111", fg="#d0d0d0",
                           insertbackground="#d0d0d0")
        sb = ttk.Scrollbar(logwrap, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill="x", **pad)
        self.cancel_btn = ttk.Button(bottom, text="Cancelar (durante la cuenta)",
                                     command=self._on_cancel, state="disabled")
        self.cancel_btn.pack(side="left")
        ttk.Button(bottom, text="Limpiar log",
                   command=self._clear_log).pack(side="right")

    def _labeled_entry(self, parent, label):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=6, pady=2)
        ttk.Label(row, text=label, width=22).pack(side="left")
        var = tk.StringVar()
        ttk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
        return var

    # ----- helpers de la GUI -----------------------------------------
    def _toggle_topmost(self):
        self.root.attributes("-topmost", self.topmost_var.get())

    def _launch_console(self, args):
        """Lanza `python <args...>` EN UNA CONSOLA NUEVA, sin tocar el panel.

        Es solo un atajo: ejecuta los mismos scripts que correrias a mano
        (la calibracion pide teclas en una terminal real via msvcrt).
        """
        cmd = [sys.executable] + list(args)
        self._emit(f"[calibracion] abriendo consola:  python {' '.join(args)}")
        kwargs = {"cwd": HERE}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        try:
            subprocess.Popen(cmd, **kwargs)
        except OSError as e:
            self._emit(f"[ERROR] no se pudo abrir la consola: {e}")

    # ----- overlays en vivo (calibracion / topologia) -------------
    OVERLAY_FILES = (
        ("coords.json", "COORDS_PATH", "#22e34a"),            # verde
        ("ip_config_coords.json", "IP_CONFIG_COORDS_PATH", "#3aa0ff"),  # azul
        ("router_coords.json", "ROUTER_COORDS_PATH", "#ff9a2e"),        # naranja
    )
    TYPE_COLORS = {
        "router": "#3aa0ff",   # azul
        "switch": "#22e34a",   # verde
    }
    TYPE_COLOR_DEFAULT = "#ff9a2e"  # naranja: pc / end devices / otros
    _CHROMA = "#ff00fe"  # color-clave: se vuelve 100% transparente

    def _refresh_overlay_buttons(self):
        self.cal_overlay_btn.configure(
            text="Ocultar overlay de calibracion" if self.overlay_kind == "cal"
            else "Mostrar overlay de calibracion")
        self.topo_overlay_btn.configure(
            text="Ocultar overlay de topologia" if self.overlay_kind == "topo"
            else "Mostrar overlay de topologia")

    def _close_overlay(self):
        if self.overlay is not None:
            try:
                self.overlay.destroy()
            except tk.TclError:
                pass
        self.overlay = None
        self.overlay_kind = None
        self._refresh_overlay_buttons()

    def _show_overlay(self, kind, markers, legend):
        """Crea el Toplevel transparente + click-through y dibuja los markers.

        markers : lista de (etiqueta, x, y, color)
        legend  : lista de (texto, color) para la esquina superior izquierda
        Devuelve True si se aplico el click-through (Windows).
        """
        self._close_overlay()
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        sw, sh = ov.winfo_screenwidth(), ov.winfo_screenheight()
        ov.geometry(f"{sw}x{sh}+0+0")

        transparent = True
        try:
            ov.configure(bg=self._CHROMA)
            ov.attributes("-transparentcolor", self._CHROMA)
        except tk.TclError:
            transparent = False
            ov.attributes("-alpha", 0.4)

        cv = tk.Canvas(ov, highlightthickness=0, bd=0,
                       bg=self._CHROMA if transparent else "#0a0a0a")
        cv.pack(fill="both", expand=True)

        y_leg = 10
        for text, color in legend:
            cv.create_rectangle(10, y_leg - 6, 24, y_leg + 6,
                                fill=color, outline="#000000")
            _otext(cv, 30, y_leg, text, color, anchor="w")
            y_leg += 22
        _otext(cv, 30, y_leg + 4,
               "clic = pasa a Packet Tracer   |   boton del panel = ocultar",
               "#ffffff", anchor="w")

        for name, x, y, color in markers:
            _draw_marker(cv, x, y, name, color)
        if not markers:
            _otext(cv, sw // 2, sh // 2, "(nada que mostrar)",
                   "#ffffff", anchor="center")

        ov.update_idletasks()
        self.overlay = ov
        self.overlay_kind = kind
        made = self._make_click_through(ov)
        self._refresh_overlay_buttons()
        return made

    def _toggle_calibration_overlay(self):
        """Overlay con los puntos de data/*coords*.json (via core.coords)."""
        if self.overlay_kind == "cal":
            self._close_overlay()
            self._emit("[overlay] calibracion: oculto.")
            return
        mods = self._load_modules()
        if mods is None:
            return
        markers, legend, total = [], [], 0
        for label, path_key, color in self.OVERLAY_FILES:
            data = mods["coords_io"].load_coords(mods[path_key])  # reutiliza core
            pts = _iter_points(data)
            legend.append((f"{label}  ({len(pts)})", color))
            for name, x, y in pts:
                markers.append((name, x, y, color))
                total += 1
        try:
            made = self._show_overlay("cal", markers, legend)
        except tk.TclError as e:
            self._emit(f"[overlay] no se pudo crear: {e}")
            self._close_overlay()
            return
        self._emit(f"[overlay] calibracion: {total} puntos"
                   + ("" if made else " (sin click-through: no es Windows)") + ".")

    def _toggle_topology_overlay(self):
        """Overlay con los dispositivos de topologia_actual.json (via core.topology)."""
        if self.overlay_kind == "topo":
            self._close_overlay()
            self._emit("[overlay] topologia: oculto.")
            return
        mods = self._load_modules()
        if mods is None:
            return
        path = mods["TOPOLOGY_ACTUAL_PATH"]
        if not os.path.exists(path):
            self._emit("[overlay] topologia: no existe data/topology/"
                       "topologia_actual.json. Usa 'Colocar' primero.")
            return
        try:
            with redirect_stdout(self.writer), redirect_stderr(self.writer):
                topo = mods["load_topology"](path)  # reutiliza core/topology.py
        except SystemExit:
            self._emit("[overlay] topologia: no se pudo leer el JSON (detalle arriba).")
            return
        devs = topo.get("dispositivos", []) if isinstance(topo, dict) else []
        if not devs:
            self._emit("[overlay] topologia: el registro no tiene dispositivos.")
            return

        markers = []
        counts = {"router": 0, "switch": 0, "pc": 0}
        for d in devs:
            tipo = str(d.get("tipo", "")).lower()
            pos = d.get("posicion") or [0, 0]
            try:
                x, y = int(round(pos[0])), int(round(pos[1]))
            except (TypeError, ValueError, IndexError):
                continue
            color = self.TYPE_COLORS.get(tipo, self.TYPE_COLOR_DEFAULT)
            nombre = d.get("nombre", "?")
            modelo = d.get("modelo")
            label = f"{nombre} ({modelo})" if modelo else nombre
            markers.append((label, x, y, color))
            counts["router" if tipo == "router" else
                   "switch" if tipo == "switch" else "pc"] += 1

        legend = []
        summary = []
        for key, singular, plural, color in (
            ("router", "router", "routers", self.TYPE_COLORS["router"]),
            ("switch", "switch", "switches", self.TYPE_COLORS["switch"]),
            ("pc", "PC", "PCs", self.TYPE_COLOR_DEFAULT),
        ):
            n = counts[key]
            if n:
                txt = f"{n} {singular if n == 1 else plural}"
                legend.append((txt, color))
                summary.append(txt)

        try:
            made = self._show_overlay("topo", markers, legend)
        except tk.TclError as e:
            self._emit(f"[overlay] no se pudo crear: {e}")
            self._close_overlay()
            return
        self._emit(f"[overlay] topologia: {', '.join(summary)}"
                   + ("" if made else " (sin click-through: no es Windows)") + ".")

    def _make_click_through(self, win):
        """WS_EX_LAYERED | WS_EX_TRANSPARENT sobre el HWND -> los clics pasan."""
        if os.name != "nt":
            return False
        try:
            import ctypes
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            GA_ROOT = 2
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.restype = ctypes.c_long
            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowLongW.restype = ctypes.c_long
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.c_long]
            hwnd = user32.GetAncestor(win.winfo_id(), GA_ROOT) or win.winfo_id()
            cur = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                  cur | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            return True
        except (OSError, AttributeError) as e:  # noqa: BLE001
            self._emit(f"[overlay] click-through no aplicado: {e}")
            return False

    def _on_opacity(self, value):
        """Slider 30-100 -> self.root -alpha 0.3-1.0, en vivo."""
        pct = int(round(float(value)))
        try:
            self.root.attributes("-alpha", pct / 100.0)
        except tk.TclError:
            pass
        self.opacity_label.configure(text=f"Opacidad: {pct}%")

    def _emit(self, msg):
        """Mensaje propio del panel (con salto de linea)."""
        self.q.put(msg.rstrip("\n") + "\n")

    def _poll_queue(self):
        chunks = []
        try:
            while True:
                chunks.append(self.q.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            text = "".join(chunks).replace("\r", "")
            self.log.configure(state="normal")
            self.log.insert("end", text)
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(80, self._poll_queue)

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_running(self, on):
        self.running = on
        state = "disabled" if on else "normal"
        for b in self._job_buttons:
            b.configure(state=state)
        self.cancel_btn.configure(state="normal" if on else "disabled")

    def _on_cancel(self):
        self._cancel.set()

    # ----- carga perezosa de los modulos del proyecto ----------------
    def _load_modules(self):
        if self._mods is not None:
            return self._mods
        try:
            import pyautogui
            import build
            import configure_ip
            import move_device
            try:
                import routers.configure_router as configure_router
            except ImportError:
                import importlib.util
                p = os.path.join(HERE, "routers", "configure_router.py")
                spec = importlib.util.spec_from_file_location(
                    "configure_router", p)
                configure_router = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(configure_router)
            from core import coords as coords_io
            from core.topology import load_topology
            from core.paths import (COORDS_PATH, IP_CONFIG_COORDS_PATH,
                                    ROUTER_COORDS_PATH, TOPOLOGY_ACTUAL_PATH)
        except ImportError as e:
            self._emit(f"[ERROR] falta una dependencia: {e}")
            self._emit("Instala con:  pip install -r requirements.txt")
            return None

        self._mods = {
            "pyautogui": pyautogui,
            "build": build,
            "configure_ip": configure_ip,
            "configure_router": configure_router,
            "move_device": move_device,
            "coords_io": coords_io,
            "load_topology": load_topology,
            "COORDS_PATH": COORDS_PATH,
            "IP_CONFIG_COORDS_PATH": IP_CONFIG_COORDS_PATH,
            "ROUTER_COORDS_PATH": ROUTER_COORDS_PATH,
            "TOPOLOGY_ACTUAL_PATH": TOPOLOGY_ACTUAL_PATH,
        }
        ok, msg = dpi_aware.verify()
        self._emit(f"DPI awareness: {dpi_aware.STATUS}")
        self._emit(("" if ok else "[!] ") + msg)
        return self._mods

    # ----- prechequeos (evitan la calibracion interactiva) ----------
    def _precheck_topology(self, m):
        if not os.path.exists(m["TOPOLOGY_ACTUAL_PATH"]):
            return ("No hay ninguna topologia colocada todavia "
                    "(data/topology/topologia_actual.json). Usa 'Colocar' primero.")
        return None

    def _precheck_ip(self, m):
        err = self._precheck_topology(m)
        if err:
            return err
        data = m["coords_io"].load_coords(m["IP_CONFIG_COORDS_PATH"])
        missing = [k for k in self.REQ_IP_COORDS if data.get(k) is None]
        if missing:
            return ("Faltan puntos calibrados en data/ip_config_coords.json: "
                    + ", ".join(missing)
                    + "\nCalibra en la terminal:  python configure_ip.py --calibrate")
        return None

    def _precheck_router(self, m):
        err = self._precheck_topology(m)
        if err:
            return err
        rdata = m["coords_io"].load_coords(m["ROUTER_COORDS_PATH"])
        if rdata.get("cli_tab") is None:
            return ("Falta 'cli_tab' en data/router_coords.json.\n"
                    "Calibra:  python routers/configure_router.py --calibrate")
        ipdata = m["coords_io"].load_coords(m["IP_CONFIG_COORDS_PATH"])
        if ipdata.get("close_button") is None:
            return ("Falta 'close_button' en data/ip_config_coords.json.\n"
                    "Calibra:  python configure_ip.py --calibrate")
        return None

    # ----- handlers de los botones ---------------------------------
    def _on_colocar(self):
        text = self.topo_text.get("1.0", "end").strip()
        if not text:
            self._emit("[ERROR] escribe una descripcion de topologia primero.")
            return
        self._start_job(
            "Colocar topologia",
            argv=["build.py", text, "--countdown", "0"],
            main_getter=lambda m: m["build"].main,
            precheck=self._precheck_topology_optional,
        )

    def _precheck_topology_optional(self, m):
        # build.py no necesita topologia previa; solo coords.json (que el
        # propio script valida). Nada que comprobar aqui.
        return None

    def _on_ip(self):
        name = self.ip_name.get().strip()
        ip = self.ip_addr.get().strip()
        mask = self.ip_mask.get().strip()
        gw = self.ip_gw.get().strip()
        if not (name and ip and mask and gw):
            self._emit("[ERROR] completa dispositivo, IP, mascara y gateway.")
            return
        for lbl, val in (("IP", ip), ("mascara", mask), ("gateway", gw)):
            if not _looks_ipish(val):
                self._emit(f"[ERROR] {lbl} '{val}' no parece IPv4 (x.x.x.x, 0-255).")
                return
        self._start_job(
            "Configurar IP",
            argv=["configure_ip.py", name, ip, mask, gw, "--countdown", "0"],
            main_getter=lambda m: m["configure_ip"].main,
            precheck=self._precheck_ip,
        )

    def _on_router(self):
        name = self.rt_name.get().strip()
        host = self.rt_host.get().strip()
        if not (name and host):
            self._emit("[ERROR] completa dispositivo y hostname.")
            return
        if not _looks_hostname(host):
            self._emit(f"[ERROR] hostname '{host}' invalido: empieza por letra, "
                       f"solo letras/digitos/guiones, sin guion final, max 63.")
            return
        self._start_job(
            "Configurar Router",
            argv=["configure_router.py", name, host, "--countdown", "0"],
            main_getter=lambda m: m["configure_router"].main,
            precheck=self._precheck_router,
        )

    def _on_move(self):
        name = self.mv_name.get().strip()
        if not name:
            self._emit("[ERROR] indica el nombre del dispositivo a mover.")
            return
        argv = ["move_device.py", name]
        if self.mv_random.get():
            argv.append("--random")
        else:
            xs, ys = self.mv_x.get().strip(), self.mv_y.get().strip()
            if not (_is_int(xs) and _is_int(ys)):
                self._emit("[ERROR] X e Y deben ser enteros, o marca 'Aleatorio'.")
                return
            argv += [xs, ys]
        argv += ["--countdown", "0"]
        self._start_job(
            "Mover dispositivo",
            argv=argv,
            main_getter=lambda m: m["move_device"].main,
            precheck=self._precheck_topology,
        )

    # ----- motor de ejecucion --------------------------------------
    def _start_job(self, label, argv, main_getter, precheck):
        if self.running:
            self._emit("[espera] ya hay una accion en curso.")
            return
        try:
            secs = max(0, int(self.countdown_var.get() or 0))
        except ValueError:
            secs = 5
        self._cancel.clear()
        self._set_running(True)
        t = threading.Thread(
            target=self._run_job,
            args=(label, list(argv), main_getter, precheck, secs),
            daemon=True,
        )
        t.start()

    def _run_job(self, label, argv, main_getter, precheck, secs):
        old_argv = sys.argv
        try:
            self._emit("")
            self._emit("=" * 40)
            self._emit(f"  {label}")
            self._emit("=" * 40)

            mods = self._load_modules()
            if mods is None:
                return

            err = precheck(mods)
            if err:
                self._emit("[ERROR] " + err)
                return

            for i in range(secs, 0, -1):
                if self._cancel.is_set():
                    self._emit("  Cancelado antes de empezar. Nada se movio.")
                    return
                self._emit(f"  Empezando en {i}...  (enfoca Packet Tracer)")
                time.sleep(1)
            if self._cancel.is_set():
                self._emit("  Cancelado. Nada se movio.")
                return

            pyautogui = mods["pyautogui"]
            pyautogui.FAILSAFE = True  # failsafe SIEMPRE activo
            pyautogui.PAUSE = 0.0

            sys.argv = argv
            self._emit(f"  (equivale a: python {' '.join(argv)})")
            with redirect_stdout(self.writer), redirect_stderr(self.writer):
                main_getter(mods)()
            self._emit(f"=== {label}: terminado ===")

        except SystemExit as e:
            code = e.code if e.code is not None else 0
            if code in (0, None):
                self._emit(f"=== {label}: terminado ===")
            else:
                self._emit(f"[fin] el script termino con codigo {code} "
                           f"(mira el detalle arriba).")
        except Exception as e:  # noqa: BLE001
            if e.__class__.__name__ == "FailSafeException":
                self._emit("[FAILSAFE] mouse en la esquina superior izquierda: "
                           "accion abortada.")
            else:
                self.q.put(traceback.format_exc())
        finally:
            sys.argv = old_argv
            self.root.after(0, lambda: self._set_running(False))


def main():
    root = tk.Tk()
    PanelControl(root)
    root.mainloop()


if __name__ == "__main__":
    main()
