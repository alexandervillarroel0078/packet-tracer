"""
Vistas del Modo visible (tkinter, solo dibujan): la barra de accion (arriba al centro,
siempre encima, sin foco y sin bloquear clics), el overlay de pantalla completa para las marcas
de destino / lineas de arrastre / recuadros de verificacion, y el visor de la ultima
calibracion. La logica esta en panel/controllers/visible.py.
"""

import tkinter as tk

from panel.overlay import CHROMA, make_click_through, _otext
from panel.controllers.visible import CLEAR, LINE, MARK, RECT

BAR_W, BAR_H = 640, 78
BAR_BG, BAR_FG = "#1b1b1b", "#ffffff"


class ActionBar:
    """Barra pequena: paso actual, accion con su duracion y rastro de fases recientes."""

    def __init__(self, root, model):
        self.root, self.model = root, model
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        sw = self.win.winfo_screenwidth()
        self.win.geometry(f"{BAR_W}x{BAR_H}+{(sw - BAR_W) // 2}+6")
        self.win.configure(bg=BAR_BG)
        self.step = tk.Label(self.win, bg=BAR_BG, fg="#9ad1ff", anchor="w",
                             font=("Segoe UI", 10, "bold"))
        self.action = tk.Label(self.win, bg=BAR_BG, fg=BAR_FG, anchor="w",
                               font=("Segoe UI", 14, "bold"))
        self.trail = tk.Label(self.win, bg=BAR_BG, fg="#9a9a9a", anchor="w",
                              font=("Segoe UI", 8))
        for w in (self.step, self.action, self.trail):
            w.pack(fill="x", padx=10)
        self.win.update_idletasks()
        make_click_through(self.win)
        self.refresh()

    def refresh(self):
        step, action, trail = self.model.bar_lines()
        self.step.configure(text=step or "Modo visible")
        self.action.configure(text=action or "Esperando una acción...")
        self.trail.configure(text=trail)

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class ScreenOverlay:
    """Pantalla completa transparente y click-through donde se dibujan las marcas."""

    def __init__(self, root):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        self.win.geometry(f"{sw}x{sh}+0+0")
        self.win.configure(bg=CHROMA)
        self.win.attributes("-transparentcolor", CHROMA)
        self.cv = tk.Canvas(self.win, highlightthickness=0, bd=0, bg=CHROMA)
        self.cv.pack(fill="both", expand=True)
        self.win.update_idletasks()
        make_click_through(self.win)
        self._n = 0

    def draw(self, cmd):
        kind = cmd["cmd"]
        if kind == CLEAR:
            self.cv.delete("all")
            return
        self._n += 1
        tag = f"m{self._n}"
        cv = self.cv
        if kind == MARK:
            x, y = cmd["point"]
            r = 18
            for width, color in ((6, "#000000"), (3, "#ffe14d")):
                cv.create_oval(x - r, y - r, x + r, y + r, outline=color, width=width, tags=tag)
                cv.create_line(x - r - 6, y, x + r + 6, y, fill=color, width=width, tags=tag)
                cv.create_line(x, y - r - 6, x, y + r + 6, fill=color, width=width, tags=tag)
            if cmd.get("name"):
                _otext(cv, x + r + 8, y - r - 8, cmd["name"], "#ffe14d", tags=tag)
        elif kind == LINE:
            (x1, y1), (x2, y2) = cmd["a"], cmd["b"]
            cv.create_line(x1, y1, x2, y2, fill="#000000", width=6, tags=tag)
            cv.create_line(x1, y1, x2, y2, fill="#4dc3ff", width=3, arrow="last", tags=tag)
        elif kind == RECT:
            l, t, w, h = cmd["rect"]
            cv.create_rectangle(l, t, l + w, t + h, outline="#000000", width=6, tags=tag)
            cv.create_rectangle(l, t, l + w, t + h, outline=cmd["color"], width=3, tags=tag)
            _otext(cv, l, t - 12, cmd["text"], cmd["color"], tags=tag)
        ttl = int(1000 * cmd.get("ttl", 1.0))
        # las marcas caducan solas; el evento "clear" las quita antes si hace falta
        self.root.after(ttl, lambda: self._expire(tag))

    def _expire(self, tag):
        try:
            self.cv.delete(tag)
        except tk.TclError:
            pass

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class VisibleView:
    """Conecta los eventos del runner con la barra y el overlay (mientras el modo esta activo)."""

    def __init__(self, root, controller):
        self.root, self.c = root, controller
        self.bar = None
        self.overlay = None

    @property
    def active(self):
        return self.bar is not None

    def set_active(self, on):
        if on and not self.active:
            self.c.model.reset()
            self.overlay = ScreenOverlay(self.root)
            self.bar = ActionBar(self.root, self.c.model)
            self.root.lift()
        elif not on and self.active:
            self.bar.close()
            self.overlay.close()
            self.bar = self.overlay = None

    def on_event(self, ev):
        """Evento de core.log. Devuelve la linea para el log (o None)."""
        if not self.active:
            return None
        for cmd in self.c.model.handle(ev):
            self.overlay.draw(cmd)
        self.bar.refresh()
        return self.c.model.log_line(ev)

    def tick(self):
        """Refresca la duracion de la fase en curso (cada ~100 ms)."""
        if self.active:
            self.bar.refresh()

    def close(self):
        self.set_active(False)


def show_image_window(root, path, title="Última calibración"):
    """Ventana con la captura enviada a la IA y los puntos devueltos."""
    win = tk.Toplevel(root)
    win.title(title)
    img = tk.PhotoImage(file=path)
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    k = max(1, -(-img.width() // int(sw * 0.9)), -(-img.height() // int(sh * 0.85)))
    if k > 1:
        img = img.subsample(k, k)
    lbl = tk.Label(win, image=img)
    lbl.image = img            # evitar que se libere
    lbl.pack()
    return win
