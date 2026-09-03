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

import time

from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
import pyautogui


def open_device_window(x, y, open_delay):
    pyautogui.doubleClick(x, y)
    time.sleep(open_delay)


def click_point(point, delay):
    pyautogui.click(point[0], point[1])
    time.sleep(delay)


def type_into(point, value, pause):
    """Clic en un campo de texto, borra lo que haya y escribe value."""
    pyautogui.click(point[0], point[1])
    time.sleep(pause)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.15)
    pyautogui.press("delete")
    time.sleep(0.15)
    pyautogui.write(str(value), interval=0.05)
    time.sleep(pause)


def close_window(close_button, pause):
    pyautogui.click(close_button[0], close_button[1])
    time.sleep(pause)


def park_mouse():
    w, h = pyautogui.size()
    pyautogui.moveTo(w // 2, h // 2)
