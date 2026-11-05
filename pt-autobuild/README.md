# pt-autobuild

Automatiza la construcción de topologías en **Cisco Packet Tracer** en Windows: coloca
dispositivos, renombra sus etiquetas, escribe notas con las redes, configura la IP de los PCs y
el hostname de los routers, y genera la configuración IOS. Todo se maneja desde un **panel**; no
hace falta usar la terminal.

> Funciona "a ciegas": mueve el mouse y teclea según unas coordenadas que **calibras una vez**
> (a mano o con ayuda de IA). Mientras actúa, el mouse y el teclado están ocupados.

## Instalación

Requisitos: Windows 10/11 y Python 3.10 o superior.

1. Descarga o clona el proyecto.
2. Crea el entorno e instala las dependencias (una sola vez), desde la carpeta del proyecto:
   ```
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
3. **Doble clic en `iniciar.bat`.** Abre el panel (usa `.venv` o `venv` si existen; si no, el
   Python del sistema).

Dependencias: `pyautogui`, `opencv-python`, `Pillow`. El panel usa `tkinter`,
que viene con Python en Windows.

## Primeros pasos (uso seguro)

1. Abre Packet Tracer y déjalo visible, sin ventanas encima, siempre con el mismo tamaño y
   posición y la misma escala de Windows.
2. En la pestaña **Simple**, pulsa **Calibrar** (ver "Calibración" más abajo).
3. En **Colocar**, pega una topología o pulsa **Cargar ejemplo**, y pulsa
   **Vista previa del plan**.
4. **Empieza siempre con Dry-run marcado** (viene marcado por defecto): calcula y muestra el
   plan sin mover el mouse. Revisa posiciones, nombres e IPs.
5. Cuando todo cuadre, **desmarca Dry-run**. Los botones cambian a rojo y a un texto que dice
   que "mueve el mouse de verdad". Pulsa y **enfoca Packet Tracer** durante la cuenta regresiva.

Seguridad mientras actúa:
- **Cuenta regresiva visible** antes de tomar el mouse (se configura arriba; 0 la desactiva).
- **DETENER** corta la cuenta regresiva y la acción en curso.
- **Failsafe de pyautogui**: lleva el mouse a la esquina superior izquierda de la pantalla para
  abortar al instante.
- Antes de construir de verdad se comprueba la calibración; si falta algo, no se mueve nada.
- Si una calibración va a **escribir en el buscador** de Packet Tracer, el log lo avisa **antes**
  de la cuenta regresiva (y todavía puedes pulsar DETENER).

## Ajustes: proveedor de IA y API key (opcional)

Solo hace falta para la **autocalibración con IA**, que puede usar **OpenAI** o **Anthropic**;
cambias de uno a otro desde el panel, sin tocar código. En la pestaña **Ajustes**:

1. Elige el **proveedor** (por defecto **OpenAI**).
2. Pega su **API key** (el campo está oculto; **Mostrar** la revela) y el **modelo**. Cada
   proveedor recuerda su propia clave y modelo.
3. **Guardar** lo escribe en `.env` (ignorado por git). Ninguna clave se imprime nunca en el
   log, en los mensajes de error ni en las excepciones.
4. **Probar conexión** hace una petición mínima con el proveedor elegido y te dice si la clave,
   el modelo y la red están bien. El log indica qué proveedor y modelo se usaron (sin la clave).

| Proveedor | Variables de `.env` | Dónde sacar la clave | Modelo |
|---|---|---|---|
| **OpenAI** | `OPENAI_API_KEY`, `OPENAI_MODEL` | https://platform.openai.com/api-keys | **Lo eliges tú** (no hay uno por defecto): debe ser un modelo con visión. |
| **Anthropic** | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | https://console.anthropic.com/settings/keys | Por defecto `claude-sonnet-5-5`. |

El proveedor activo es `AI_PROVIDER=openai` o `AI_PROVIDER=anthropic` (el selector de Ajustes lo
escribe). También puedes editar `.env` a mano; hay una plantilla en `.env.example`.

Si la API falla, el panel lo explica: clave inválida, sin saldo o cuota, modelo inexistente o sin
visión, límite de uso, sin red o timeout.

> **Cambiar de proveedor o de modelo invalida la caché** de la autocalibración: la siguiente
> pasada vuelve a llamar a la IA. Si cambias de proveedor, **comprueba** lo detectado con
> **Solo mostrar** antes de guardar: cada modelo puede equivocarse de forma distinta. Si un modelo
> devuelve coordenadas normalizadas (0-1) o fuera de la imagen, se **rechazan** con un aviso en
> el log en vez de guardarse.

También verás el **informe de DPI**: debe decir que `pyautogui` y la resolución física
coinciden. Si no, los clics se desviarán.

> Privacidad: la autocalibración envía al proveedor activo (OpenAI o Anthropic) una **captura de
> la ventana de Packet Tracer** (de toda la pantalla si no la encuentra). Cierra lo que no quieras
> enviar.

## Modo visible (ver todo en vivo)

En la pestaña **Simple**, la casilla **Modo visible** (desmarcada por defecto) muestra el proceso
mientras ocurre. Al marcarla aparecen dos ventanas que **no roban el foco ni bloquean tus clics**
(los clics las atraviesan):

- **Barra de acción** (arriba al centro, siempre encima): el paso actual y su resultado en
  lenguaje simple, con la **duración de cada fase**. Por ejemplo `Paso 3/8: colocar PC1`,
  `Clic en el buscador`, `Escribiendo: 2960`, `Tecla: Ctrl+A`, `Esperando que filtre (1.0 s)`,
  `Arrastrando al lienzo`, `Verificando punto: OK 0.97`, `Consultando a la IA... 6.2 s`. Debajo
  queda el rastro de las últimas fases con lo que tardó cada una.
- **Overlay de pantalla**: antes de cada clic dibuja ~0.5 s un círculo con cruz en el destino y
  el nombre del punto (`search_field`, `filtered_result`...); en un arrastre, la línea de origen
  a destino. Al verificar un punto resalta el recorte buscado (**verde** si coincide, **rojo**
  si no) con su porcentaje de confianza.

Con el modo visible, el mouse se mueve con `moveTo` y duración (**Duración del mouse**, entre
0.4 y 0.8 s) y hace una pausa corta antes de cada clic.

Controles (todos en el recuadro «Modo visible»):

| Control | Qué hace |
|---|---|
| **Velocidad** (Rápido / Normal / Lento) | Escala **todas** las pausas y duraciones (×0.5, ×1, ×2), con o sin modo visible. |
| **Pausa / Continuar** | Congela la acción hasta continuar. |
| **Paso a paso** + **Siguiente ▶** | Espera tu confirmación antes de cada clic. |
| **DETENER** / failsafe | Siguen activos, también durante una pausa o una espera de «Siguiente». |

> Pausa y Siguiente son botones del panel: al pulsarlos el panel toma el foco; el siguiente clic
> de la automatización devuelve el foco a Packet Tracer.

**Dry-run + modo visible = simulación visual:** recorre todos los pasos de **Construir**
mostrando los destinos en el overlay y el texto en la barra, **sin mover el mouse real ni hacer
clics** (no hay cuenta regresiva y no se guarda el registro de topología). Si el mouse llega a la
esquina superior izquierda, el failsafe aborta igual.

**Calibrar:** cada autocalibración guarda la captura enviada a la IA con los puntos devueltos
dibujados en `data/ultima_calibracion.png`; el botón **Ver última calibración** de Simple la abre
(un punto rechazado por la regla geométrica sale en rojo).

### Cómo está hecho

- `core/log.py`: **una sola función** `emit(texto, kind, point=..., name=...)`. Los mensajes
  (`kind="log"`) siguen yendo al log; las acciones (`click`, `type`, `key`, `wait`, `drag`,
  `verify`, `ai`, `step`) llegan como `Event` a los *listeners*. La barra, el overlay y el log del
  modo visible leen de ahí.
- `core/hands.py`: **todo** clic, tecla, arrastre y espera de `automation/` y `core/` pasa por
  aquí. Con el modo visible apagado equivale a llamar a `pyautogui` directamente.
- `core/visual.py`: estado (visible, simulación, velocidad, pausa, paso a paso).
- Ni `core/` ni `automation/` usan tkinter; el dibujo vive en `panel/visible_view.py` y la
  lógica en `panel/controllers/visible.py`.

## Las pestañas

### Colocar
- Caja de **topología**: sintaxis simple (`2 routers, 2 switches, 4 PC`) o por redes (abajo).
- **Cargar ejemplo** (`config/ejemplos/`) y **Cargar archivo** (`.txt`, o `.json` con
  `comando_original`, como el registro que genera la herramienta).
- **Vista previa del plan** y **Comprobar calibración** (re-verifica en pantalla, sin API).
- **Construir** (dry-run por defecto). Si la calibración no está lista, no actúa y aparece
  **Recalibrar y continuar**: autocalibra lo que falta con IA y construye si queda listo.
- **Mover dispositivo**: arrastra uno ya colocado a otra posición (X Y o aleatoria) y actualiza
  el registro. Usa el mismo Dry-run.

Construir coloca cada dispositivo (buscador → resultado → lienzo), renombra su etiqueta, escribe
las notas de CIDR/interfaces/enlaces y configura IP, máscara y gateway de los PCs. Guarda el
registro en `data/topology/`.

### Configurar
- **IP en PCs**: elige el PC, o aplica la IP del registro a **todos**. Opción para "ventana ya
  abierta en IP Configuration".
- **Hostname de routers** por CLI (`enable` → `configure terminal` → `hostname`).
- **Generar configuración**: configuración IOS de los routers (interfaces + rutas **estáticas**
  o **RIP**) a partir de la topología de Colocar, con vista previa y **Copiar**. Solo cálculo.
- Dry-run marcado por defecto, igual que en Colocar.

### Calibración
Lo único visible es el **estado resumido** y el botón **Calibrar** (con su Dry-run, marcado por
defecto). Es el mismo botón que en la pestaña Simple:

1. **Verifica sin API** y sin tocar el mouse: mira la pantalla y comprueba los puntos guardados.
2. Si todo coincide, muestra **"Ya está calibrado"**.
3. Si no, **autocalibra solo el grupo main** con IA (requiere la API key de Ajustes), con cuenta
   regresiva y el aviso previo de que va a escribir en el buscador (un modelo de prueba, 2911, que
   se borra después). Al terminar resume en lenguaje simple **qué quedó bien** y **qué hay que
   hacer a mano**.

Con **Dry-run** marcado solo verifica y explica lo que haría; no calibra ni guarda.

#### Herramientas de depuración (sección plegable, cerrada por defecto)
Todo lo demás está aquí. Las herramientas de IA actúan sobre el grupo **main**:

| Botón | Qué hace |
|---|---|
| **Solo mostrar** | Dry-run: muestra lo detectado, **no guarda y no toca el mouse**. |
| **Forzar** | Autocalibra ignorando la caché; escribe en el buscador. |
| **Verificar** | Sin API y sin mouse: re-verifica los puntos guardados y marca los que ya no coinciden. |

Además:
- **Tabla de estado** por elemento (los 16, de todos los grupos): **OK**, **requiere manual** o
  **sin verificar**.
- **Captura manual con F8**: elige un punto, pulsa *Capturar punto*, mueve el mouse y pulsa
  **F8** (ESC cancela). También *Calibrar ventana IP*, *Calibrar router (CLI)*, *Calibrar cable*
  y *Calibrar por imágenes de referencia*.
- **Overlays**: dibujan sobre la pantalla los puntos calibrados o los dispositivos colocados
  (los clics pasan a Packet Tracer).

#### Cable e IP: se calibran bajo demanda
Los grupos **cable** e **ip** no tienen botones permanentes ni selector. Cuando una acción real
(p. ej. **Aplicar IP**) detecta que falta calibrar, **no actúa**: aparece un asistente sobre las
pestañas con la instrucción exacta (p. ej. *"Abre la ventana de IP de una PC en la pestaña
Desktop"*) y un botón **Continuar** que calibra **solo ese grupo** (con Dry-run, cuenta regresiva
y DETENER). La ventana de IP se pide en dos pasos (Desktop, y luego IP Configuration con Static);
el asistente cambia la instrucción cuando termina el primero. Con Dry-run, Continuar solo
explica. Vuelve a pulsar la acción original cuando el asistente diga que está listo.

### Ajustes
Proveedor de IA, API key, modelo, prueba de conexión e informe de DPI (ver arriba).

## Qué dejar abierto para cada calibración

La IA indica qué estados de la interfaz ve. Si falta uno, **no adivina**: deja ese elemento sin
tocar y te dice qué abrir. **Calibrar** solo usa el primer grupo; para cable e ip es lo que te
pide el asistente cuando hace falta.

| Grupo | Qué calibra | Déjalo así en Packet Tracer |
|---|---|---|
| **main** (`coords.json`) | `search_field`, `filtered_result`, esquinas del lienzo | Packet Tracer visible, sin ventanas ni menús encima. Para `filtered_result` se usa el buscador: se escribe un modelo de prueba y se limpia. |
| **cable** (`cable_coords.json`) | `cable_icon`, `cable_icons.*`, `list_offset`, `list_row_height` | Categoría de conexiones (rayo) seleccionada, con los **tipos** de cable en la paleta inferior. Para la lista de interfaces: con un cable armado, clic en un dispositivo y **deja el mouse quieto encima** con la lista desplegada. |
| **ip** (`ip_config_coords.json`) | `desktop_tab`, `close_button`, `ip_configuration_item`, `static_radio` y los 3 campos | Doble clic en un PC (ventana abierta, sin moverla). **Pasada 1:** pestaña *Desktop* (iconos). **Pasada 2:** *Desktop → IP Configuration* con *Static* marcado. Son excluyentes: una pasada cada vez. |

`filtered_result` se omite si hay un menú o ventana abierta; calíbralo en una pasada **main**
aparte. Con la caché, si la resolución, la escala DPI, la posición de la ventana, el **proveedor y el
modelo** no cambiaron y los recortes siguen en su sitio, **no se llama a la API**.

La verificación (`matchTemplate`) confirma que el punto cae sobre algo reconocible y estable;
**no** que la IA haya elegido el elemento correcto. Revisa con **Solo mostrar** o con el overlay.

### Imágenes de referencia (calibrar por imágenes)

*Calibrar por imágenes de referencia* busca en pantalla tres recortes PNG de `reference_images/`
(nombres exactos):

| Archivo | Qué recortar | Para qué |
|---|---|---|
| `search_field.png` | El campo **"Search for device"** (con la lupa) | Su centro es `search_field`; su borde superior es el borde inferior del lienzo |
| `top_toolbar.png` | Un trozo distintivo de la barra superior (3-5 botones) | Su borde inferior es el borde superior del lienzo |
| `right_toolbar.png` | Un trozo distintivo de la barra vertical derecha (2-4 botones) | Su borde izquierdo es el borde derecho del lienzo |

Recórtalos con la Herramienta de Recortes de Windows: con Packet Tracer en su posición y tamaño
habituales y la **misma escala de Windows** que usarás después; recorte ajustado (~2 px), sin
cursor, tooltip ni resaltado; en **PNG** y con Packet Tracer totalmente visible. Los recortes
`auto_*.png` los genera la autocalibración y no se versionan.

## Sintaxis de la topología

Simple: `3 routers modelo 4331, 2 switches, 5 PC, 1 tablet` (tipos: router, switch, pc, laptop,
tablet, server, smartphone; modelo opcional, ver `config/device_catalog.json`).

Por redes (permite IPs y enlaces; ver `config/ejemplos/`):
```
SWITCHES: Sw1, Sw2
ROUTERS: R01, R02
RED Red1: 192.168.10.0/24 R01     # R01 es el gateway (.1)
PC1 .2
PC2                               # IP autoasignada
ENLACES:
R01 Se0/1/0 R02 10.0.0.0/30
```

## Archivos y carpetas

```
app.py  iniciar.bat           punto de entrada (panel)
panel/                        interfaz: una vista por pestaña + controllers/ (sin tkinter)
automation/                   lo que mueve el mouse: build, configure_ip, configure_router,
                              cable_link, add_note, rename_label, move_device, calibrate
core/                         lógica pura y utilidades: topology, config_gen, autocalibrate,
                              preflight, settings, coords, ventanas y DPI, y el modo visible
                              (log de eventos, hands, visual)
config/                       device_catalog.json, topologia_ejemplo.json, ejemplos/
data/                         coordenadas, registro de topología, estado del panel (no se versiona)
reference_images/             recortes de referencia
tests/                        pytest
```

`data/` y `.env` son propios de cada equipo y no se versionan.

## Limitaciones

- **El cableado automático aún no existe.** Al construir solo se **calcula** el plan de cables
  (el log lo muestra); los cables se conectan a mano. Las funciones de `automation/cable_link.py`
  están probadas, pero no están integradas en el panel; cuando lo estén, el asistente de cable
  (ya implementado, `AsistenteController.ensure("cable")`) se encargará de pedir su calibración.
- **Las coordenadas dependen de la resolución, la escala de Windows y la posición/tamaño de la
  ventana de Packet Tracer.** Si cambias cualquiera de ellas, pulsa **Calibrar**.
- Solo Windows (DPI, captura de puntos con F8). Un solo monitor principal.
- Todo es "a ciegas": no lee la pantalla durante la construcción. Si Packet Tracer pierde el
  foco o aparece un diálogo, los clics caerán donde no deben (usa **DETENER** o el failsafe).
- El renombrado de etiquetas está confirmado a mano solo para routers (offset de 38 px);
  switches y PCs usan el mismo valor sin confirmar.
- La autocalibración con IA necesita red y una API key (OpenAI o Anthropic), envía capturas al proveedor y puede equivocarse
  de elemento; la verificación visual lo mitiga, no lo elimina.
- Solo se escribe ASCII de forma fiable (acentos y eñes pueden salir mal al teclear).

## Problemas frecuentes

- **Un error inesperado** se resume en el log del panel; el detalle técnico queda en
  `data/panel_errors.log`.
- **"Falta la API key"** (o el modelo): configúralos en Ajustes para el proveedor activo.
- **Los clics caen desfasados**: mira el informe de DPI en Ajustes y mantén la misma escala de
  Windows que al calibrar.

## Pruebas

```
.venv\Scripts\pip install pytest
.venv\Scripts\python -m pytest
```

Los tests bloquean `pyautogui` (ninguno puede mover el mouse ni teclear) y redirigen `data/` y
`.env` a una carpeta temporal. Los tests del modo visible (`tests/test_visible.py`) cubren los
eventos, las duraciones y la velocidad con `pyautogui` sustituido por un grabador.
