"""
panel.overlay - overlays transparentes y click-through sobre la pantalla (calibracion /
topologia). Es dibujo puro: los datos los entrega panel/controllers/calibracion.py.
"""

import os
import tkinter as tk

CHROMA = "#ff00fe"          # color-clave: se vuelve 100% transparente
TYPE_COLORS = {"router": "#3aa0ff", "switch": "#22e34a"}
TYPE_COLOR_DEFAULT = "#ff9a2e"


def _otext(cv, x, y, text, color, anchor="w"):
    cv.create_text(x + 1, y + 1, text=text, fill="#000000", anchor=anchor,
                   font=("Segoe UI", 9, "bold"))
    cv.create_text(x, y, text=text, fill=color, anchor=anchor, font=("Segoe UI", 9, "bold"))


def _marker(cv, x, y, name, color):
    r = 7
    cv.create_line(x - r, y - r, x + r, y + r, fill="#000000", width=4)
    cv.create_line(x - r, y + r, x + r, y - r, fill="#000000", width=4)
    cv.create_line(x - r, y - r, x + r, y + r, fill=color, width=2)
    cv.create_line(x - r, y + r, x + r, y - r, fill=color, width=2)
    _otext(cv, x + r + 3, y, name, color)


def make_click_through(win):
    """WS_EX_LAYERED | WS_EX_TRANSPARENT sobre el HWND: los clics pasan al de abajo."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
        hwnd = user32.GetAncestor(win.winfo_id(), 2) or win.winfo_id()
        cur = user32.GetWindowLongW(hwnd, -20)
        user32.SetWindowLongW(hwnd, -20, cur | 0x00080000 | 0x00000020)
        return True
    except (OSError, AttributeError):
        return False


class OverlayManager:
    def __init__(self, root, notify):
        self.root, self.notify = root, notify
        self.window = None
        self.kind = None

    def close(self):
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
        self.window = None
        self.kind = None

    def _labels(self, cal_btn, topo_btn):
        cal_btn.configure(text="Ocultar overlay de calibracion" if self.kind in ("cal", "det")
                          else "Mostrar overlay de calibracion")
        topo_btn.configure(text="Ocultar overlay de topologia" if self.kind == "topo"
                           else "Mostrar overlay de topologia")

    def _show(self, kind, markers, legend):
        self.close()
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        sw, sh = ov.winfo_screenwidth(), ov.winfo_screenheight()
        ov.geometry(f"{sw}x{sh}+0+0")
        transparent = True
        try:
            ov.configure(bg=CHROMA)
            ov.attributes("-transparentcolor", CHROMA)
        except tk.TclError:
            transparent = False
            ov.attributes("-alpha", 0.4)
        cv = tk.Canvas(ov, highlightthickness=0, bd=0, bg=CHROMA if transparent else "#0a0a0a")
        cv.pack(fill="both", expand=True)
        y = 10
        for text, color in legend:
            cv.create_rectangle(10, y - 6, 24, y + 6, fill=color, outline="#000000")
            _otext(cv, 30, y, text, color)
            y += 22
        _otext(cv, 30, y + 4, "clic = pasa a Packet Tracer   |   boton del panel = ocultar",
               "#ffffff")
        for name, x, yy, color in markers:
            _marker(cv, x, yy, name, color)
        if not markers:
            _otext(cv, sw // 2, sh // 2, "(nada que mostrar)", "#ffffff", anchor="center")
        ov.update_idletasks()
        self.window, self.kind = ov, kind
        return make_click_through(ov)

    def toggle_calibration(self, groups, cal_btn, topo_btn):
        """groups = [(archivo, color, [(nombre, x, y)...])]"""
        if self.kind in ("cal", "det"):
            self.close()
            self.notify("[overlay] calibracion: oculto.")
        else:
            markers, legend = [], []
            for label, color, pts in groups:
                legend.append((f"{label}  ({len(pts)})", color))
                markers += [(n, x, y, color) for n, x, y in pts]
            self._show("cal", markers, legend)
            self.notify(f"[overlay] calibracion: {len(markers)} puntos.")
        self._labels(cal_btn, topo_btn)

    def show_detected(self, points, cal_btn, topo_btn):
        """points = [(nombre, x, y, rechazado)]: lo detectado por la IA en 'Solo mostrar'."""
        markers = [(f"{n} (RECHAZADO)" if bad else n, x, y, "#ff3b3b" if bad else "#ffe14d")
                   for n, x, y, bad in points]
        legend = [("detectado por la IA (no guardado)", "#ffe14d")]
        if any(p[3] for p in points):
            legend.append(("rechazado por geometria", "#ff3b3b"))
        self._show("det", markers, legend)
        self.notify(f"[overlay] detectado: {len(markers)} punto(s). Se oculta con el boton "
                    "de overlay de calibracion.")
        self._labels(cal_btn, topo_btn)

    def toggle_topology(self, devices, cal_btn, topo_btn):
        """devices = [(etiqueta, x, y, tipo)]"""
        if self.kind == "topo":
            self.close()
            self.notify("[overlay] topologia: oculto.")
        else:
            counts = {"router": 0, "switch": 0, "pc": 0}
            markers = []
            for label, x, y, tipo in devices:
                markers.append((label, x, y, TYPE_COLORS.get(tipo, TYPE_COLOR_DEFAULT)))
                counts[tipo if tipo in ("router", "switch") else "pc"] += 1
            legend = [(f"{n} {k}", TYPE_COLORS.get(k, TYPE_COLOR_DEFAULT))
                      for k, n in counts.items() if n]
            self._show("topo", markers, legend)
            self.notify("[overlay] topologia: " + ", ".join(t for t, _ in legend) + ".")
        self._labels(cal_btn, topo_btn)
