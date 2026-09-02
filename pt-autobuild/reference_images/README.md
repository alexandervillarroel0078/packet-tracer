# reference_images/

Recortes PNG que `calibrate.py` busca en pantalla con `pyautogui.locateOnScreen()`.

Nombres EXACTOS (minusculas, extension .png):

| Archivo | Que recortar |
|---|---|
| `router_icon.png` | Icono de la categoria **Routers** en la barra inferior |
| `switch_icon.png` | Icono de la categoria **Switches** en la barra inferior |
| `pc_icon.png` | Icono de la categoria **End Devices** en la barra inferior |
| `router_model.png` | Icono del **modelo concreto** de router que uses (ej. 2911), con la categoria Routers abierta |
| `switch_model.png` | Icono del modelo concreto de switch (ej. 2960), con Switches abierta |
| `pc_model.png` | Icono del modelo **PC**, con End Devices abierta |
| `top_toolbar.png` | Un trozo distintivo de la barra de herramientas **superior** (3-5 botones) |
| `right_toolbar.png` | Un trozo distintivo de la barra de herramientas **vertical derecha** (2-4 botones) |

Reglas al recortar (Herramienta de Recortes de Windows):

- Packet Tracer en su posicion y tamaño habituales, los mismos que usaras con `build.py`.
- Escala de pantalla de Windows igual que al ejecutar (idealmente 100 %).
- Recorte **ajustado** al icono, con ~2 px de borde. Ni demasiado grande ni al ras.
- **Sin** cursor del mouse, sin tooltip, sin resaltado de hover ni de seleccion encima.
- Guardar como **PNG** (no JPG: los artefactos rompen el match).
- Packet Tracer totalmente visible, sin ventanas encima, al recortar y al calibrar.
