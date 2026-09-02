import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui (fija DPI awareness)
import pyautogui
import time

print(f"DPI awareness: {dpi_aware.STATUS}")
_ok, _msg = dpi_aware.verify()
print(f"Verificacion : {_msg}")

print("Cuenta regresiva: 5 segundos para cambiar el foco a Packet Tracer...")
for i in range(5, 0, -1):
    print(i)
    time.sleep(1)

pyautogui.FAILSAFE = True

try:
    location = pyautogui.locateOnScreen("reference_images/search_field.png", confidence=0.8)
    if location:
        center = pyautogui.center(location)
        print(f"Campo de busqueda encontrado en: {center}")
        pyautogui.click(center)
        time.sleep(0.3)
        pyautogui.typewrite("4331", interval=0.05)
        print("Texto '4331' escrito. Revisa Packet Tracer para confirmar.")
    else:
        print("No se encontró la imagen search_field.png en pantalla.")
except Exception as e:
    print(f"Error: {e}")
