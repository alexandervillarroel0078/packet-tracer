# pt-autobuild

Automatiza la **colocacion mecanica** de dispositivos en Cisco Packet Tracer
mediante clics a ciegas con `pyautogui`. Proyecto independiente de pt-asistente.

Alcance a proposito limitado:

- Solo coloca dispositivos genericos en el lienzo.
- NO dibuja cables.
- NO lee la pantalla (sin OCR, sin verificacion). Confia en las coordenadas calibradas.
- NO configura ni renombra nada.

## Instalacion

```
pip install -r requirements.txt
```

## Escala de Windows / DPI

Con la escala de pantalla de Windows distinta al 100 % (p. ej. 125 %), pyautogui
por defecto trabaja en coordenadas "logicas" escaladas mientras que las capturas
son en pixeles fisicos -> los clics se desvian.

**No hay que cambiar la configuracion de Windows.** El proyecto lo compensa solo:
[dpi_aware.py](dpi_aware.py) marca el proceso como *DPI aware* (per-monitor v2,
con fallbacks) y se importa lo primero en `calibrate.py`, `build.py` y
`test_search.py`. A partir de ahi, tamaño de pantalla, raton, capturas y clics
van todos en pixeles fisicos reales y coinciden.

Comprueba que funciona:

```
python check_dpi.py           # informe
python check_dpi.py --watch   # + posicion del raton en vivo
```

Debe decir `pyautogui.size() == resolucion fisica`. Con `--watch`, al mover el
raton a la esquina inferior derecha debe leer la resolucion fisica completa
(no una menor).

> Recorta las imagenes de referencia y ejecuta siempre con la **misma** escala de
> Windows. La Herramienta de Recortes de Windows 11 ya captura en pixeles fisicos,
> asi que tus recortes actuales deberian servir; si algo no matchea tras el fix,
> vuelve a recortar esa imagen.

## 1. Calibracion (hazlo primero) — automatica por imagen

`calibrate.py` localiza los iconos de Packet Tracer en pantalla con
`pyautogui.locateOnScreen()`, a partir de recortes PNG que preparas una vez en
[reference_images/](reference_images/). Ya no hay que apuntar el mouse a mano.

### 1a. Preparar las imagenes de referencia

Con Packet Tracer abierto en su posicion habitual y **modo "Network Devices"**
activo, recorta con la Herramienta de Recortes de Windows y guarda como PNG en
`reference_images/` (nombres exactos, ver [reference_images/README.md](reference_images/README.md)):

| Archivo | Que recortar |
|---|---|
| `router_icon.png` / `switch_icon.png` / `pc_icon.png` | Icono de cada **categoria** en la barra inferior |
| `router_model.png` / `switch_model.png` / `pc_model.png` | Icono del **modelo concreto** (con esa categoria abierta) |
| `top_toolbar.png` | Trozo distintivo de la barra **superior** (3-5 botones) |
| `right_toolbar.png` | Trozo distintivo de la barra **vertical derecha** (2-4 botones) |

Reglas: recorte ajustado (~2 px de borde), sin cursor ni tooltip ni resaltado
encima, PNG (no JPG), misma escala de pantalla que al calibrar/construir.

Comprueba que estan todas:

```
python calibrate.py --list
```

### 1b. Ejecutar la calibracion

```
python calibrate.py                  # completa
python calibrate.py --confidence 0.80 # baja el umbral si algo no matchea
python calibrate.py --grayscale       # match en gris (a veces mas robusto)
python calibrate.py --manual-models    # Fase B sin autoclic: abres tu cada categoria
python calibrate.py --no-models        # no tocar los modelos
```

- **Fase A** (sin mover el mouse): localiza los 3 iconos de categoria y las 2
  anclas de barras.
- **Fase B** (modelos): como el panel de modelos solo aparece con su categoria
  abierta, por defecto el script **hace clic** en cada icono de categoria (con
  cuenta regresiva de 5 s + failsafe) y luego localiza el modelo. Con
  `--manual-models` lo abres tu y pulsas ENTER (no se mueve el mouse).
- **Lienzo**: se calcula como el espacio entre la barra superior
  (`top_toolbar.png`), la barra derecha (`right_toolbar.png`) y la fila de
  iconos de categoria; el borde izquierdo es fijo. Si falta un ancla, se estima
  por porcentaje de pantalla y se avisa.
- Si una imagen no matchea, el resumen dice **cual** y por que; corrige ese
  recorte y reejecuta, o captura ese punto a mano:

```
python calibrate.py --manual canvas:top_left
python calibrate.py --manual categories:router
```

- Salida: `coords.json` (mismo formato que antes; `build.py` no cambia). Se
  escribe de forma atomica y se verifica en disco.

## 2. Construccion

```
python build.py "4 routers, 4 switches, 8 PCs"
python build.py --file topologia.txt
python build.py "2 routers, 3 switches, 12 pcs" --dry-run
```

Opciones:

| Opcion | Efecto |
|---|---|
| `--file RUTA` | Lee la topologia desde un archivo de texto (acepta `#` como comentario) |
| `--dry-run` | Calcula e imprime el plan **sin** mover el mouse |
| `--pause SEG` | Pausa entre clics (def. `0.4`). Subela si Packet Tracer va lento |
| `--countdown N` | Segundos de cuenta regresiva antes de empezar (def. `5`) |

Sintaxis de topologia: pares `<numero> <tipo>` en cualquier orden, separados por
comas o saltos de linea. Sinonimos: `router/routers/r`, `switch/switches/sw`,
`pc/pcs/host/computer`. Ejemplos: `4 routers, 4 switches, 8 PCs` o `4x router`.

Layout automatico: routers en la fila de arriba, switches en la fila siguiente,
y los PCs repartidos en columnas debajo de cada switch (o en cuadricula si no
hay switches). Todo dentro del rectangulo `canvas.top_left` -> `canvas.bottom_right`.

Secuencia por dispositivo: clic en icono de categoria -> clic en icono de modelo
-> clic en la posicion calculada del lienzo, con `--pause` entre cada clic.

**Prueba siempre con `--dry-run` primero** para revisar las coordenadas antes de
soltar el mouse.

### Seguridad

- Cuenta regresiva de 5 s antes del primer clic (cambia el foco a Packet Tracer).
- Failsafe de pyautogui activo: lleva el mouse a la **esquina superior izquierda
  de la pantalla** para abortar de inmediato.
- Pausa configurable entre cada clic.
- Al terminar imprime un resumen de cuantos dispositivos se intentaron colocar.
