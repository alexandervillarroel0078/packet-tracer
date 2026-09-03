"""
core.topology - lectura del registro topologia_actual.json que genera build.py.

    load_topology(path)          -> dict   (sale con error si no existe / ilegible)
    find_device(topology, name)  -> dict   (sale con error listando los nombres)
"""

import json
import os
import sys


def load_topology(path):
    if not os.path.exists(path):
        print(f"ERROR: no existe {path}")
        print("  Corre build.py primero (sin --dry-run) para generar el registro.")
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: no se pudo leer {path}: {e}")
        sys.exit(1)


def find_device(topology, name):
    devs = topology.get("dispositivos", [])
    for d in devs:
        if str(d.get("nombre", "")).lower() == name.lower():
            return d
    print(f"ERROR: no hay ningun dispositivo llamado '{name}' en el registro.")
    print("  Disponibles:", ", ".join(d.get("nombre", "?") for d in devs))
    sys.exit(1)
