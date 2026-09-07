"""
core.paths - rutas absolutas del proyecto.

Todo lo especifico de la maquina (coordenadas, topologias generadas) vive en
data/ y esta en .gitignore. Lo versionable (catalogo, imagenes de referencia)
vive en la raiz.
"""

import os

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CORE_DIR)

# --- versionable (va a git) ------------------------------------------
CATALOG_PATH = os.path.join(PROJECT_ROOT, "device_catalog.json")
REFERENCE_IMAGES_DIR = os.path.join(PROJECT_ROOT, "reference_images")
TOPOLOGY_EXAMPLE_PATH = os.path.join(PROJECT_ROOT, "topologia_ejemplo.json")

# --- especifico de la maquina / generado (gitignored, data/) --------
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
COORDS_PATH = os.path.join(DATA_DIR, "coords.json")
IP_CONFIG_COORDS_PATH = os.path.join(DATA_DIR, "ip_config_coords.json")
ROUTER_COORDS_PATH = os.path.join(DATA_DIR, "router_coords.json")
CABLE_COORDS_PATH = os.path.join(DATA_DIR, "cable_coords.json")

TOPOLOGY_DIR = os.path.join(DATA_DIR, "topology")
TOPOLOGY_HISTORY_DIR = os.path.join(TOPOLOGY_DIR, "history")
TOPOLOGY_ACTUAL_PATH = os.path.join(TOPOLOGY_DIR, "topologia_actual.json")
