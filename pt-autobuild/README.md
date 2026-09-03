# pt-autobuild

Automatiza tareas repetitivas en Cisco Packet Tracer moviendo el mouse y el
teclado (pyautogui), "a ciegas": no lee la pantalla, confia en coordenadas
calibradas una vez.

## Instalacion

```
cd pt-autobuild
pip install -r requirements.txt
```

Todos los comandos se ejecutan **desde la carpeta `pt-autobuild/`**.

## Flujos

| Script | Que hace |
|---|---|
| `python check_dpi.py` | Comprueba que pyautogui trabaja en pixeles fisicos (necesario para que los clics caigan bien con escala de Windows ≠ 100%). |
| `python calibrate.py` | Genera `data/coords.json`: campo de busqueda, resultado filtrado y rectangulo del lienzo. Correr una vez (o tras mover/redimensionar Packet Tracer). |
| `python build.py "3 routers modelo 4331, 2 switches modelo 2960, 5 PC, 1 tablet"` | Coloca los dispositivos en el lienzo y guarda el registro en `data/topology/` (`topologia_actual.json` + historico con fecha). `--dry-run` para ver el plan sin tocar el mouse. |
| `python configure_ip.py PC0 192.168.10.10 255.255.255.0 192.168.10.1` | Abre la ventana del PC (por su nombre en `topologia_actual.json`), va a Desktop > IP Configuration > Static y escribe los 3 campos. `--calibrate` la primera vez. `--skip-open` si la ventana ya esta abierta (depurar). |
| `python routers/configure_router.py Router0 R01` | Abre la ventana del router, va a la pestana CLI y cambia el hostname. `--calibrate` la primera vez. Reutiliza `close_button` de `data/ip_config_coords.json`. |

Cada script de configuracion pide calibrar sus puntos la primera vez (mover el
mouse al elemento + **ESPACIO**). Todos aceptan `--dry-run` y `--recalibrate`.

## Estructura

```
pt-autobuild/
├── core/                 logica compartida (sin estado)
│   ├── dpi_aware.py      marca el proceso DPI-aware (importar antes que pyautogui)
│   ├── paths.py          rutas absolutas del proyecto
│   ├── coords.py         load/save de los JSON de coordenadas + captura manual
│   ├── validate.py       validacion de formato (IPv4, hostname)
│   ├── ptwindow.py       abrir/cerrar la ventana, escribir en campos
│   └── topology.py       leer topologia_actual.json, buscar dispositivo por nombre
├── build.py              colocacion de dispositivos + registro de topologia
├── calibrate.py          calibracion del lienzo
├── check_dpi.py          diagnostico de DPI/coordenadas
├── configure_ip.py       config IP de PCs
├── routers/
│   └── configure_router.py   hostname de routers via CLI
├── device_catalog.json   modelos validos (versionado)
├── topologia_ejemplo.json    formato del registro, con datos ficticios (versionado)
├── reference_images/     recortes PNG para calibrate.py
└── data/                 GENERADO / especifico de la maquina (gitignored)
    ├── coords.json
    ├── ip_config_coords.json
    ├── router_coords.json
    └── topology/
        ├── topologia_actual.json
        └── history/topologia_<fecha>.json
```

`data/` no esta en git y se crea solo al correr `calibrate.py` / `build.py`.

## Alcance

Coloca y configura lo minimo; **no cablea** y **no persiste** la config de los
routers (`copy run start` queda fuera). Los cables se conectan a mano.
