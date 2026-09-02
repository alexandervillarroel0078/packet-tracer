# reference_images/

Recortes PNG que `calibrate.py` busca en pantalla con `pyautogui.locateOnScreen()`.

Nombres EXACTOS (minusculas, extension .png):

| Archivo | Que recortar | Para que |
|---|---|---|
| `search_field.png` | El campo **"Search for device"** (con la lupa), tal como se ve al abrir Packet Tracer | Centro = `search_field`; su borde superior = borde inferior del lienzo |
| `top_toolbar.png` | Un trozo distintivo de la barra de herramientas **superior** (3-5 botones) | Borde inferior = borde superior del lienzo |
| `right_toolbar.png` | Un trozo distintivo de la barra de herramientas **vertical derecha** (2-4 botones) | Borde izquierdo = borde derecho del lienzo |

`filtered_result` (la posicion fija del icono filtrado) NO se recorta: se calibra
a mano una sola vez con `calibrate.py` (o `calibrate.py --manual filtered_result`).

Reglas al recortar (Herramienta de Recortes de Windows):

- Packet Tracer en su posicion y tamaño habituales, los mismos que usaras con `build.py`.
- **Misma escala de Windows** al recortar y al calibrar/construir (el proyecto ya
  compensa la escala via `dpi_aware.py`, pero los recortes deben ser coherentes entre si).
- Recorte **ajustado** (~2 px de borde), sin cursor, sin tooltip, sin resaltado de hover/seleccion.
- Guardar como **PNG** (no JPG).
- Packet Tracer totalmente visible, sin ventanas encima.
