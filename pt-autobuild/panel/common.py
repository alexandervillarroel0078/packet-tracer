"""
panel.common - piezas de interfaz compartidas (tkinter): log en vivo, barra de estado con
cuenta regresiva + progreso + boton Detener, boton con modo (dry-run / actua de verdad) y
pestanas con scroll. Solo dibujan; la logica vive en panel/controllers.
"""

import tkinter as tk
from tkinter import ttk

COLOR_DRY = "#2e7d32"        # verde: no actua
COLOR_REAL = "#b71c1c"       # rojo: actua de verdad
COLOR_STOP = "#c62828"
FONT_BTN = ("Segoe UI", 9, "bold")


class LogView(ttk.LabelFrame):
    """Log en vivo (solo lectura)."""

    def __init__(self, parent, height=9):
        super().__init__(parent, text="Log")
        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True, padx=6, pady=6)
        self.text = tk.Text(wrap, height=height, width=42, wrap="word", state="disabled",
                            bg="#111", fg="#d0d0d0", insertbackground="#d0d0d0")
        sb = ttk.Scrollbar(wrap, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("error", foreground="#ff6b6b")
        self.text.tag_configure("warn", foreground="#ffd166")

    def append(self, msg):
        msg = str(msg).replace("\r", "")
        tag = None
        if msg.lstrip().startswith(("[ERROR", "ERROR")):
            tag = "error"
        elif msg.lstrip().startswith(("[!]", "[detenido]", "[FAILSAFE]", "[espera]")):
            tag = "warn"
        self.text.configure(state="normal")
        self.text.insert("end", msg.rstrip("\n") + "\n", tag or ())
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class StatusBar(ttk.Frame):
    """Estado + cuenta regresiva grande + barra de progreso + boton DETENER."""

    def __init__(self, parent, on_stop):
        super().__init__(parent)
        self.countdown = tk.Label(self, text="", font=("Segoe UI", 14, "bold"),
                                  fg="#ffffff", bg="#e65100")
        self.state = ttk.Label(self, text="Listo.", anchor="w")
        self.state.pack(fill="x")
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(2, 0))
        self.progress = ttk.Progressbar(row, mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.stop = tk.Button(row, text="DETENER", command=on_stop, state="disabled",
                              bg=COLOR_STOP, fg="white", font=FONT_BTN, relief="raised",
                              disabledforeground="#e0a0a0")
        self.stop.pack(side="right")

    def set_state(self, state, label=""):
        busy = state != "idle"
        self.stop.configure(state="normal" if busy else "disabled")
        if state == "idle":
            self.state.configure(text="Listo.")
            self.progress.stop()
            self.countdown.pack_forget()
        elif state == "countdown":
            self.state.configure(text=f"{label}: cuenta regresiva...")
        else:
            self.state.configure(text=f"Ejecutando: {label}")
            self.countdown.pack_forget()
            if str(self.progress["mode"]) != "determinate" or self.progress["value"] == 0:
                self.set_progress(0, 0)

    def set_tick(self, seconds):
        if seconds > 0:
            self.countdown.configure(
                text=f"  Empezando en {seconds}...  enfoca Packet Tracer  "
                     "(DETENER o mouse a la esquina sup-izq = abortar)  ")
            self.countdown.pack(fill="x", before=self.state)
        else:
            self.countdown.pack_forget()

    def set_progress(self, done, total):
        if total > 0:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=100.0 * done / total)
        else:
            self.progress.configure(mode="indeterminate")
            self.progress.start(15)


class ModeButton(tk.Button):
    """Boton que cambia de texto y color segun actue o no de verdad (modo dry-run)."""

    def __init__(self, parent, text_dry, text_real, command, **kw):
        self.text_dry, self.text_real = text_dry, text_real
        kw.setdefault("font", FONT_BTN)
        super().__init__(parent, command=command, fg="white", relief="raised", **kw)
        self.real = False
        self.set_real(False)

    def set_real(self, real):
        self.real = bool(real)
        self.configure(text=self.text_real if real else self.text_dry,
                       bg=COLOR_REAL if real else COLOR_DRY,
                       activebackground="#d32f2f" if real else "#388e3c")


def bind_mode(button, dry_var):
    """Sincroniza un ModeButton con un BooleanVar de 'Dry-run' (marcado = no actua)."""
    def refresh(*_):
        button.set_real(not dry_var.get())
    dry_var.trace_add("write", refresh)
    refresh()


class CollapsibleFrame(ttk.Frame):
    """Seccion plegable (cerrada por defecto). El contenido va en .body."""

    def __init__(self, parent, text, opened=False):
        super().__init__(parent)
        self.text = text
        self.opened = False
        self.toggle_btn = ttk.Button(self, command=self.toggle)
        self.toggle_btn.pack(fill="x")
        self.body = ttk.Frame(self)
        self.set_opened(opened)

    def set_opened(self, opened):
        self.opened = bool(opened)
        self.toggle_btn.configure(text=("▾ " if self.opened else "▸ ") + self.text)
        if self.opened:
            self.body.pack(fill="both", expand=True)
        else:
            self.body.pack_forget()

    def toggle(self):
        self.set_opened(not self.opened)


def make_scroll_tab(notebook, text, height=360):
    """Pestana con scroll vertical interno. Devuelve (frame_contenido, canvas)."""
    page = ttk.Frame(notebook)
    notebook.add(page, text=text)
    cv = tk.Canvas(page, height=height, highlightthickness=0, bd=0)
    vsb = ttk.Scrollbar(page, orient="vertical", command=cv.yview)
    cv.configure(yscrollcommand=vsb.set)
    vsb.pack(side="right", fill="y")
    cv.pack(side="left", fill="both", expand=True)
    inner = ttk.Frame(cv)
    win = cv.create_window((0, 0), window=inner, anchor="nw")

    def sync(event):
        cv.itemconfigure(win, width=event.width)
        cv.itemconfigure(win, height=max(inner.winfo_reqheight(), event.height))

    inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
    cv.bind("<Configure>", sync)
    return inner, cv
