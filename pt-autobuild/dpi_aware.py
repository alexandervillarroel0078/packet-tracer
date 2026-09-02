"""
dpi_aware.py - Marca el proceso de Python como "DPI aware" en Windows.

IMPORTA ESTE MODULO LO PRIMERO, ANTES QUE pyautogui / pyscreeze / PIL,
en cada script del proyecto:

    import dpi_aware  # noqa: F401  (debe ir antes de pyautogui)
    import pyautogui
    ...

Por que hace falta
------------------
Con la escala de Windows distinta al 100 % (p. ej. 125 %), un proceso Python
"DPI unaware" recibe de Windows una resolucion VIRTUAL reducida (1536x864 en vez
de 1920x1080) y coordenadas de raton escaladas. Pero la captura de pantalla de
pyautogui (via Pillow) se hace en PIXELES FISICOS reales. Ese desajuste hace que
locateOnScreen encuentre la imagen en unas coordenadas y el clic caiga en otras
(el famoso "desfase de coordenadas").

Al marcar el proceso como DPI aware, TODO -- tamaño de pantalla, posicion del
raton, capturas y clics -- queda en pixeles fisicos reales y coincide, sin tener
que tocar la configuracion de escala de Windows.

Uso
---
El modulo se auto-ejecuta al importarse. Despues puedes consultar:
    dpi_aware.STATUS            -> texto de que via se aplico
    dpi_aware.physical_size()   -> (w, h) fisicos reales del monitor primario
    dpi_aware.verify()          -> (ok: bool, mensaje: str) comparando con pyautogui
"""

import sys

STATUS = "no aplicado (no es Windows)"


def make_process_dpi_aware():
    """Intenta la mejor via disponible. Idempotente. Devuelve STATUS."""
    global STATUS
    if sys.platform != "win32":
        return STATUS

    import ctypes

    # 1) Windows 10 1703+  ->  PER_MONITOR_AWARE_V2  (la opcion correcta hoy)
    try:
        fn = ctypes.windll.user32.SetProcessDpiAwarenessContext
        fn.restype = ctypes.c_bool
        fn.argtypes = [ctypes.c_void_p]
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == -4
        if fn(ctypes.c_void_p(-4)):
            STATUS = "PER_MONITOR_AWARE_V2 (SetProcessDpiAwarenessContext -4)"
            return STATUS
    except (AttributeError, OSError):
        pass

    # 2) Windows 8.1+  ->  PROCESS_PER_MONITOR_DPI_AWARE (== 2)
    try:
        hres = ctypes.windll.shcore.SetProcessDpiAwareness(2)
        # S_OK (0) o E_ACCESSDENIED (ya estaba fijado por manifiesto) -> OK
        if hres == 0 or (hres & 0xFFFFFFFF) == 0x80070005:
            STATUS = "PER_MONITOR_DPI_AWARE (SetProcessDpiAwareness 2)"
            return STATUS
    except (AttributeError, OSError):
        pass

    # 3) Windows Vista+  ->  system DPI aware (sin argumentos)
    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            STATUS = "SYSTEM_DPI_AWARE (SetProcessDPIAware)"
            return STATUS
    except (AttributeError, OSError):
        pass

    STATUS = "NO se pudo marcar DPI aware -- las coordenadas pueden desfasar"
    return STATUS


def physical_size():
    """
    (w, h) fisicos reales del monitor primario, leidos de EnumDisplaySettings.
    Este valor NO depende de la DPI awareness del proceso, sirve de referencia.
    Devuelve None fuera de Windows o si falla.
    """
    if sys.platform != "win32":
        return None
    import ctypes

    class DEVMODE(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", ctypes.c_wchar * 32),
            ("dmSpecVersion", ctypes.c_ushort),
            ("dmDriverVersion", ctypes.c_ushort),
            ("dmSize", ctypes.c_ushort),
            ("dmDriverExtra", ctypes.c_ushort),
            ("dmFields", ctypes.c_ulong),
            ("dmPositionX", ctypes.c_long),
            ("dmPositionY", ctypes.c_long),
            ("dmDisplayOrientation", ctypes.c_ulong),
            ("dmDisplayFixedOutput", ctypes.c_ulong),
            ("dmColor", ctypes.c_short),
            ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short),
            ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short),
            ("dmFormName", ctypes.c_wchar * 32),
            ("dmLogPixels", ctypes.c_ushort),
            ("dmBitsPerPel", ctypes.c_ulong),
            ("dmPelsWidth", ctypes.c_ulong),
            ("dmPelsHeight", ctypes.c_ulong),
            ("dmDisplayFlags", ctypes.c_ulong),
            ("dmDisplayFrequency", ctypes.c_ulong),
            ("dmICMMethod", ctypes.c_ulong),
            ("dmICMIntent", ctypes.c_ulong),
            ("dmMediaType", ctypes.c_ulong),
            ("dmDitherType", ctypes.c_ulong),
            ("dmReserved1", ctypes.c_ulong),
            ("dmReserved2", ctypes.c_ulong),
            ("dmPanningWidth", ctypes.c_ulong),
            ("dmPanningHeight", ctypes.c_ulong),
        ]

    ENUM_CURRENT_SETTINGS = -1
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    ok = ctypes.windll.user32.EnumDisplaySettingsW(
        None, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)
    )
    if not ok:
        return None
    return (int(dm.dmPelsWidth), int(dm.dmPelsHeight))


def verify():
    """
    Compara pyautogui.size() con la resolucion fisica real.
    Devuelve (ok, mensaje). ok=True significa que pyautogui ya trabaja en
    pixeles fisicos (la DPI awareness surtio efecto).
    """
    try:
        import pyautogui
    except ImportError:
        return False, "pyautogui no instalado"

    pa = tuple(pyautogui.size())
    phys = physical_size()
    if phys is None:
        return True, f"pyautogui.size()={pa} (sin referencia fisica; no-Windows?)"
    if pa == phys:
        return True, (f"OK: pyautogui.size()={pa} == resolucion fisica {phys}. "
                      f"Las coordenadas estan en pixeles fisicos.")
    return False, (f"DESFASE: pyautogui.size()={pa} != resolucion fisica {phys}. "
                   f"El proceso sigue sin ser DPI aware; los clics se desviaran.")


# se ejecuta al importar
make_process_dpi_aware()
