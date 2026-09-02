# pt-autobuild

Automatiza la **colocacion mecanica** de dispositivos en Cisco Packet Tracer
mediante clics a ciegas con `pyautogui`. Proyecto independiente de pt-asistente.

Alcance a proposito limitado:

- Solo coloca dispositivos en el lienzo.
- NO dibuja cables.
- NO lee la pantalla (sin OCR, sin verificacion). Confia en `coords.json` y en el catalogo.
- NO configura ni renombra nada.

## Instalacion

```
pip install -r requirements.txt
```

## Flujo de colocacion (por buscador)

El buscador "Search for device" de Packet Tracer es **global y siempre visible**,
asi que no hace falta abrir ninguna categoria. Cada dispositivo se coloca asi:

```
1. clic en search_field
2. Ctrl+A + Supr                 (limpiar texto previo)
3. escribir el nombre del modelo (filtra en vivo, sin Enter)
4. esperar a que filtre
5. clic en filtered_result       (posicion fija del icono unico)
6. clic en la posicion calculada del lienzo
```

## Escala de Windows / DPI

Con la escala de Windows distinta al 100 % (p. ej. 125 %), pyautogui por defecto
trabaja en coordenadas "logicas" escaladas mientras que las capturas son en
pixeles fisicos -> los clics se desvian.

**No hay que cambiar la configuracion de Windows.** [dpi_aware.py](dpi_aware.py)
marca el proceso como *DPI aware* y se importa lo primero en `calibrate.py`,
`build.py`, `test_place.py`, `test_search.py` y `check_dpi.py`. A partir de ahi
todo va en pixeles fisicos reales.

```
python check_dpi.py           # informe
python check_dpi.py --watch   # + posicion del raton en vivo
```

Debe decir `pyautogui.size() == resolucion fisica`.

## 1. Calibracion

Genera `coords.json` con 4 datos: `search_field`, `filtered_result`,
`canvas.top_left`, `canvas.bottom_right`.

### 1a. Imagenes de referencia (una vez)

En [reference_images/](reference_images/), PNG con nombres exactos
(detalle en [reference_images/README.md](reference_images/README.md)):

| Archivo | Que recortar |
|---|---|
| `search_field.png` | El campo "Search for device" tal como se ve al abrir Packet Tracer |
| `top_toolbar.png` | Trozo distintivo de la barra de herramientas superior (3-5 botones) |
| `right_toolbar.png` | Trozo distintivo de la barra vertical derecha (2-4 botones) |

Recorte ajustado (~2 px), sin cursor/tooltip/hover, PNG, misma escala de Windows
que al construir. Comprueba: `python calibrate.py --list`

### 1b. Ejecutar

```
python calibrate.py                        # completa
python calibrate.py --confidence 0.80      # baja el umbral si algo no matchea
python calibrate.py --grayscale
python calibrate.py --manual filtered_result   # recapturar solo ese punto
python calibrate.py --manual canvas_top_left   # forzar una esquina a mano
```

- **Fase A** (sin mover el mouse): localiza las 3 imagenes. Guarda el centro de
  `search_field`.
- **filtered_result**: unico punto manual. El script te pide que en Packet Tracer
  hagas clic en el buscador, escribas un modelo (ej. `4331`), y cuando aparezca el
  icono unico lleves el mouse a su centro y pulses **ESPACIO**. Solo se pide si
  falta (o con `--recapture-result` / `--manual filtered_result`).
- **Lienzo**: borde superior = base de `top_toolbar.png`; borde derecho = lado
  izquierdo de `right_toolbar.png`; borde inferior = parte superior de
  `search_field.png`; borde izquierdo = fijo. Si falta un ancla, se estima por
  porcentaje de pantalla y se avisa.
- `coords.json` se escribe de forma atomica y se verifica en disco.

## 2. Catalogo de modelos

[device_catalog.json](device_catalog.json) — editable por ti:

```jsonc
{
  "defaults":    { "routers": "4331", "switches": "2960", "end_devices": "PC" },
  "routers":     ["1841", "1941", "2811", ...],
  "switches":    ["2950T", "2960", "3560", ...],
  "end_devices": ["PC", "Laptop", "Tablet", "Server", "Smartphone"]
}
```

Los nombres deben ser **exactos tal como los busca tu Packet Tracer** (la busqueda
no distingue mayusculas). Ver el catalogo actual: `python build.py --list-models`

## 3. Construccion

```
python build.py "4 routers, 4 switches, 8 PCs" --dry-run
python build.py "3 routers modelo 4331, 2 switches modelo 2960, 5 PC, 1 tablet"
python build.py --file topologia.txt
```

### Sintaxis de topologia

Clausulas separadas por comas o saltos de linea: `<n> <tipo> [modelo <M>]`

- `<tipo>`: `router(s)`, `switch(es)`, `pc(s)`, `laptop`, `tablet`, `server`,
  `smartphone`, `end device(s)`, `host`, `computer`.
- `modelo <M>`: opcional. Sin el se usa el default del catalogo. `pc`, `tablet`,
  etc. ya implican su modelo. Tambien vale token suelto al final (`3 routers 4331`).
- Se valida contra el catalogo; si el modelo no existe, aborta listando los disponibles.
- `#` inicia comentario.

Ejemplos:

```
3 routers modelo 4331
2 switches
5 PC
1 tablet
```

### Opciones

| Opcion | Efecto |
|---|---|
| `--file RUTA` | Topologia desde archivo de texto |
| `--catalog RUTA` | Catalogo alternativo (def. `device_catalog.json`) |
| `--dry-run` | Calcula e imprime el plan **sin** mover el mouse |
| `--list-models` | Imprime el catalogo y sale |
| `--pause SEG` | Pausa entre clics (def. `0.4`) |
| `--filter-delay SEG` | Espera tras escribir, antes de clicar el resultado (def. `0.4`) |
| `--countdown N` | Cuenta regresiva antes de empezar (def. `5`) |

### Layout

Routers en la fila de arriba, switches en la siguiente, end devices repartidos en
columnas debajo de cada switch (o en cuadricula si no hay switches). Varios grupos
de la misma categoria se concatenan en su fila. Todo dentro de
`canvas.top_left` -> `canvas.bottom_right`.

**Prueba siempre con `--dry-run` primero.**

### Seguridad

- Cuenta regresiva antes del primer clic.
- Failsafe de pyautogui: mouse a la **esquina superior izquierda** = aborta.
- Pausa configurable entre clics.
- Resumen final: cuantos dispositivos se intentaron colocar por categoria.

## Utilidades

| Script | Para que |
|---|---|
| `check_dpi.py` | Verificar que las coordenadas = pixeles fisicos |
| `test_place.py <modelo>` | Probar el flujo de 6 pasos con **un** dispositivo (`--save` guarda los puntos en `coords.json`) |
| `test_search.py` | Prueba minima: buscar un modelo y escribir en el campo |
