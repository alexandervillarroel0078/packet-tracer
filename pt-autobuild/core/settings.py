"""
core.settings - lectura/escritura de .env (API key y modelo de la autocalibracion).

Nunca imprime ni registra la key: ni los mensajes de error la incluyen. La escritura es
atomica y conserva el resto de lineas del .env. Tambien actualiza os.environ para que el
cambio valga en el proceso actual sin reiniciar.
"""

import os
import re

from core import paths
from core.errors import PTError

KEY_VAR = "ANTHROPIC_API_KEY"
MODEL_VAR = "ANTHROPIC_MODEL"
DEFAULT_MODEL = "claude-sonnet-5-5"

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _unquote(v):
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse_env(text):
    """{VAR: valor} de un texto .env (ignora comentarios y lineas invalidas)."""
    out = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = _LINE_RE.match(line)
        if m:
            out[m.group(1)] = _unquote(m.group(2))
    return out


def read_settings():
    """{"api_key", "model", "has_key"} desde .env (o, si falta, del entorno)."""
    values = {}
    path = paths.ENV_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                values = parse_env(f.read())
        except OSError:
            values = {}
    key = (values.get(KEY_VAR) or os.environ.get(KEY_VAR) or "").strip()
    model = (values.get(MODEL_VAR) or os.environ.get(MODEL_VAR) or "").strip() or DEFAULT_MODEL
    return {"api_key": key, "model": model, "has_key": bool(key)}


def mask_key(key):
    """Version no reversible para mostrar: primeros 7 y ultimos 4 caracteres."""
    key = key or ""
    if len(key) <= 10:
        return "*" * len(key)
    return key[:7] + "..." + key[-4:]


def validate(api_key, model):
    """Lanza PTError (sin incluir la key en el mensaje) si algo no es valido."""
    if not (api_key or "").strip():
        raise PTError("escribe la API key.")
    if re.search(r"\s", api_key.strip()):
        raise PTError("la API key no puede contener espacios ni saltos de linea.")
    if not (model or "").strip():
        raise PTError("escribe el modelo (por ejemplo " + DEFAULT_MODEL + ").")
    if re.search(r"[^A-Za-z0-9._:\-]", model.strip()):
        raise PTError("el modelo solo puede tener letras, numeros y . _ : -")


def save_settings(api_key, model):
    """Guarda ANTHROPIC_API_KEY y ANTHROPIC_MODEL en .env. Devuelve la ruta del archivo."""
    validate(api_key, model)
    api_key, model = api_key.strip(), model.strip()
    path = paths.ENV_PATH
    lines = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError as e:
            raise PTError(f"no se pudo leer {path}: {type(e).__name__}") from e
    wanted = {KEY_VAR: api_key, MODEL_VAR: model}
    done = set()
    out = []
    for line in lines:
        m = _LINE_RE.match(line)
        if m and not line.lstrip().startswith("#") and m.group(1) in wanted:
            out.append(f"{m.group(1)}={wanted[m.group(1)]}")
            done.add(m.group(1))
        else:
            out.append(line)
    for var, val in wanted.items():
        if var not in done:
            out.append(f"{var}={val}")
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out) + "\n")
        os.replace(tmp, path)
    except OSError as e:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise PTError(f"no se pudo guardar {path}: {type(e).__name__}") from e
    os.environ[KEY_VAR] = api_key
    os.environ[MODEL_VAR] = model
    return path
