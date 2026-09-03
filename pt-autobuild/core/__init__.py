"""
core - logica compartida de pt-autobuild (sin estado propio).

    dpi_aware  marca el proceso DPI-aware en Windows (importar ANTES que pyautogui)
    paths      rutas absolutas del proyecto (data/, config, coords, topologia...)
    coords     load/save de los JSON de coordenadas + captura manual de puntos
    validate   validaciones de formato (IPv4, hostname)
    ptwindow   interaccion con la ventana emergente de un dispositivo
    topology   lectura de topologia_actual.json (buscar dispositivo por nombre)

Este paquete NO importa pyautogui al cargarse: los submodulos que lo necesitan
(coords, ptwindow) importan primero 'core.dpi_aware', asi el orden es correcto
independientemente de quien los importe.
"""
