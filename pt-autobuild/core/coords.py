"""
core.coords - lectura/escritura de los JSON de coordenadas y captura de puntos.

    load_coords(path)         -> dict  (o {} si no existe / no se puede leer)
    save_coords(path, data)   -> bool  (escritura atomica + verificacion, anade screen_size)
    capture_point(label, ...) -> [x, y] | None  (mueve el mouse + F8; ESC cancela)

Sin sys.exit() ni print(): los mensajes salen por core.log.emit y los fallos graves
son excepciones (core.errors).
"""

import json
import os
import sys
import time

from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
import pyautogui

from core.errors import PTError
from core.log import emit

VK_ESCAPE = 0x1B
VK_F8 = 0x77


def load_coords(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        emit(f"  Aviso: {os.path.basename(path)} existe pero no se pudo leer; se ignora.")
        return {}


def save_coords(path, data):
    """Escribe el JSON de forma atomica (con screen_size) y verifica que quedo."""
    data["screen_size"] = list(pyautogui.size())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as e:
        emit(f"  ERROR al guardar {os.path.basename(path)}: {type(e).__name__}: {e}")
        emit("  Causas: permisos (Controlled Folder Access / antivirus), carpeta "
             "sincronizada (OneDrive) o el archivo abierto en otro programa.")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return False
    except TypeError as e:
        emit(f"  ERROR: datos no serializables a JSON: {e}")
        return False
    ok = os.path.exists(path)
    emit(f"  {'OK' if ok else 'ERROR'}: {os.path.basename(path)} "
         f"{'guardado y verificado' if ok else 'NO se escribio'}.")
    return ok


def _key_down(vk):
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def capture_point(label, previous=None, *, countdown=0, cancel=None, timeout=180,
                  poll=0.03, key_down=None):
    """
    Captura la posicion del mouse al pulsar F8 (funciona aunque la ventana activa sea
    Packet Tracer; no necesita consola). ESC cancela. Devuelve [x, y] o None
    (ESC, `cancel` activado o timeout).

    countdown  segundos de cuenta regresiva visible (emit) antes de empezar a escuchar
    cancel     threading.Event; si se activa, cancela
    key_down   funcion vk -> bool (inyectable para pruebas; def. GetAsyncKeyState)
    """
    if key_down is None:
        if sys.platform != "win32":
            raise PTError("la captura de puntos con F8 solo esta disponible en Windows.")
        key_down = _key_down
    emit(f"  Captura de '{label}': mueve el mouse al punto exacto y pulsa F8 "
         "(ESC cancela).")
    if previous is not None:
        emit(f"  (valor actual: {previous})")
    for i in range(int(countdown), 0, -1):
        emit(f"    capturando en {i}...")
        time.sleep(1)
    while key_down(VK_F8):  # suelta F8 si venia pulsado
        time.sleep(poll)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cancel is not None and cancel.is_set():
            emit("    cancelado.")
            return None
        if key_down(VK_ESCAPE):
            emit("    cancelado.")
            return None
        if key_down(VK_F8):
            x, y = pyautogui.position()
            p = [int(x), int(y)]
            emit(f"    -> {p}")
            return p
        time.sleep(poll)
    emit("    tiempo agotado sin pulsar F8.")
    return None
