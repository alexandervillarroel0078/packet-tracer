"""
core.ptwindow - interaccion con la ventana emergente de configuracion de un
dispositivo en Packet Tracer.

La ventana abre siempre en la misma posicion de pantalla mientras no se mueva
ni cambie la resolucion, asi que los puntos (pestanas, radios, boton X) se
calibran una vez como coordenadas fijas.

    open_device_window(x, y, open_delay)   doble clic en el dispositivo del lienzo
    click_point(point, delay)              clic en un punto fijo + espera
    type_into(point, value, pause)         clic + Ctrl+A + Supr + escribir value
    close_window(close_button, pause)      clic en la X
    park_mouse()                           mouse a un sitio neutro (centro)
"""

from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
from core import hands


def open_device_window(x, y, open_delay):
    hands.click(x, y, "dispositivo", double=True, text="Doble clic en el dispositivo")
    hands.sleep(open_delay)


def click_point(point, delay, name=None):
    hands.click(point[0], point[1], name)
    hands.sleep(delay)


def type_into(point, value, pause, name=None):
    """Clic en un campo de texto, borra lo que haya y escribe value."""
    hands.click(point[0], point[1], name)
    hands.sleep(pause)
    hands.hotkey("ctrl", "a")
    hands.sleep(0.15)
    hands.press("delete")
    hands.sleep(0.15)
    hands.type_text(value, interval=0.05)
    hands.sleep(pause)


def close_window(close_button, pause):
    hands.click(close_button[0], close_button[1], "close_button", text="Clic en cerrar la ventana")
    hands.sleep(pause)


def park_mouse():
    hands.park()
