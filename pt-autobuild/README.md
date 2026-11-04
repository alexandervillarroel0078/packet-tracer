cd C:\Users\Alexader\Downloads\pack-trace\pt-autobuild
copy .env.example .env
python panel_control.py

## Autocalibracion con IA (vision)

Evita la calibracion manual: una captura de Packet Tracer se envia a la API de
Anthropic, que devuelve la posicion de los elementos que `calibrate.py` pide
(`search_field`, `filtered_result`, esquinas del lienzo). Se guarda en el mismo
`data/coords.json`, mas una seccion `autocalibrate` (resolucion, escala DPI,
ventana, estado y confianza por elemento).

### Configuracion

```
pip install -r requirements.txt
copy .env.example .env          # y rellena ANTHROPIC_API_KEY
```

`.env` esta en `.gitignore`; la clave nunca se imprime en logs. `ANTHROPIC_MODEL`
(por defecto `claude-sonnet-5-5`) es opcional.

### Uso

```
python calibrate.py --auto              # detecta, verifica y guarda
python calibrate.py --auto --dry-run    # solo muestra lo detectado, no guarda
python calibrate.py --auto --force      # ignora la cache y vuelve a llamar a la API
python calibrate.py --auto --only main  # solo un grupo: main | cable | ip (varios: main,cable)
python calibrate.py --check             # SIN API: re-verifica lo guardado y dice que ya no coincide
```

Grupos (`--only`, por defecto `all`):

| Grupo | Archivo | Elementos |
|---|---|---|
| `main` | `data/coords.json` | `search_field`, `filtered_result`, `canvas.top_left`, `canvas.bottom_right` |
| `cable` | `data/cable_coords.json` | `cable_icon`, `cable_icons.<tipo>` (serial, copper y los que ya tengas), `list_offset`, `list_row_height` |
| `ip` | `data/ip_config_coords.json` | `desktop_tab`, `ip_configuration_item`, `static_radio`, `close_button`, `ipv4_address`, `subnet_mask`, `default_gateway` |

En `panel_control.py` -> pestana **Calibracion** -> **Autocalibrar (IA)** (y una
variante "solo mostrar, sin guardar").

### Como funciona

1. Captura la ventana de Packet Tracer (si no la encuentra, usa toda la pantalla).
   La captura se redimensiona (lado mayor 1568 px) y las coordenadas devueltas se
   convierten a pantalla real teniendo en cuenta el redimensionado y la escala DPI.
2. **Verificacion:** por cada punto se recorta una region de 96x96 px, se guarda en
   `reference_images/auto_<elemento>.png` y se busca con `cv2.matchTemplate` en una
   captura **nueva**; debe aparecer en el mismo sitio con confianza >= 0.90 (y el
   recorte no puede ser una zona plana). Si falla, se reintenta hasta 2 veces
   pidiendo a la IA que afine sobre un recorte ampliado de esa zona. Si sigue fallando
   el elemento queda como **requiere manual** (`python calibrate.py --manual <nombre>`).
3. **Cache:** si resolucion, escala DPI y posicion de la ventana no cambiaron y los
   recortes guardados siguen encontrandose en su sitio, **no se llama a la API**.

### filtered_result automatico

Tras verificar `search_field`, el script hace clic en el, escribe un modelo de prueba
(`--test-model`, por defecto `2911`), espera ~1 s, toma otra captura, pide a la IA **solo** la
posicion del primer resultado filtrado, lo verifica con `matchTemplate` y **limpia el buscador**
(Ctrl+A, Supr; tambien si algo falla a mitad). Con `--dry-run` no se escribe nada en la app:
solo se informa de lo que se haria. Se omite si ya tiene valor (usa `--force` para recalcularlo)
o si hay un menu/ventana abierto que el clic estropearia.

### Que dejar abierto en pantalla antes de `--auto`

Algunos elementos solo existen con cierta parte de la UI visible. La IA indica que **estados**
ve; para cada elemento cuyo estado no esta presente **no adivina**: lo deja sin tocar y te dice
que falta abrir. Puedes combinar los estados compatibles en una misma pasada:

| Estado | Que dejar en pantalla | Elementos que habilita |
|---|---|---|
| `main` | Packet Tracer visible, sin ventanas encima | `search_field`, lienzo, `filtered_result`, `cable_icon` |
| `cable_palette` | Clic en la categoria de conexiones (rayo): la paleta inferior muestra los **tipos** de cable | `cable_icons.*` |
| `interface_menu` | Con un cable armado, clic en un dispositivo del lienzo y **dejar el mouse quieto encima**: la lista de interfaces debe seguir desplegada | `list_offset`, `list_row_height` |
| `ip_window` | Doble clic en un PC: ventana abierta (pestanas y boton X) | `desktop_tab`, `close_button` |
| `ip_desktop` | En esa ventana, pestana **Desktop** (iconos de aplicaciones) | `ip_configuration_item` |
| `ip_config` | En esa ventana, **Desktop > IP Configuration** con **Static** marcado | `static_radio`, `ipv4_address`, `subnet_mask`, `default_gateway` |

Pasadas tipicas (`ip_desktop` e `ip_config` son excluyentes, asi que van por separado):

1. `main` + `cable_palette` + `interface_menu`: `python calibrate.py --auto --only main,cable`
2. Ventana de PC en Desktop: `python calibrate.py --auto --only ip`
3. Ventana de PC en IP Configuration (Static): `python calibrate.py --auto --only ip`

`list_offset` se calcula como (primer item de la lista) - (posicion del mouse, donde hiciste
clic en el dispositivo) y `list_row_height` como la distancia entre los items 0 y 1; si los valores
no son plausibles se rechazan en vez de guardarse. `filtered_result` se omite mientras haya un
menu o ventana abierto, asi que calibralo en una pasada `--only main` aparte.

Con `--auto` (todos los grupos) los elementos cuyo estado falta no se tocan y la salida termina
con codigo 1 listando que abrir. La cache solo exige lo imprescindible (`search_field`, lienzo y
`cable_icon` verificados); lo que depende de menus/ventanas basta con que tenga valor o recorte.

### Re-verificar sin API (`--check`)

`python calibrate.py --check` (opcional `--only`, `--dry-run`) no llama a la API: re-busca con
`matchTemplate` el recorte de cada punto guardado y marca los que ya no coinciden (util tras
cambiar resolucion, escala o layout). Un punto de `main` que no coincide queda **requiere manual**;
uno que depende de un menu/ventana que no esta abierto queda **sin verificar** (no se puede
afirmar nada sin verlo). Los valores calibrados a mano, sin recorte, tambien salen **sin verificar**.

### Estado por elemento en el panel

En `panel_control.py` -> pestana **Calibracion** hay una tabla con cada elemento y su estado
(boton **Actualizar estado**; se lee de los JSON, sin tocar pantalla ni API):

- **OK**: valor guardado y verificado con su recorte.
- **requiere manual**: sin valor, o la verificacion fallo / dejo de coincidir.
- **sin verificar**: hay valor (p. ej. manual) pero nunca se verifico o no se pudo verificar ahora.

El boton "Re-verificar puntos guardados (--check, sin API)" abre la consola con `--check`.

Notas:
- La verificacion confirma que el punto cae sobre algo visualmente reconocible y
  estable, no que la IA haya elegido el elemento correcto: revisa con `--dry-run` o
  con "Mostrar overlay de calibracion" del panel.
- Errores claros ante falta de `ANTHROPIC_API_KEY`, clave rechazada, modelo inexistente,
  limite de uso o falta de red. Codigos de salida: 0 ok, 1 quedan puntos manuales, 2 error.

### Pruebas

```
pip install pytest
python -m pytest
```

Cubren solo la logica pura (conversion de coordenadas, parseo/validacion del JSON de la IA
incluidos los estados de UI, geometria de la lista de interfaces, registro de elementos,
decision de cache, estados OK / manual / sin verificar), sin pantalla ni red.
