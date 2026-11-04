"""
core.settings - lectura/escritura de .env: proveedor de IA y, por proveedor, clave y modelo.

Variables:
    AI_PROVIDER=openai | anthropic        (por defecto openai)
    OPENAI_API_KEY / OPENAI_MODEL         (OpenAI no trae modelo por defecto: se configura)
    ANTHROPIC_API_KEY / ANTHROPIC_MODEL

Nunca imprime ni registra una clave: ni los mensajes de error la incluyen. La escritura es
atomica y conserva el resto de lineas del .env (tambien las del otro proveedor). Tambien
actualiza os.environ para que el cambio valga en el proceso actual sin reiniciar.
"""

import os
import re

from core import paths
from core.ai_providers import (DEFAULT_MODELS, DEFAULT_PROVIDER, KEY_VARS, LABELS, MODEL_VARS,
                               PROVIDERS, normalize_provider)
from core.errors import PTError

PROVIDER_VAR = "AI_PROVIDER"
DEFAULT_MODEL = DEFAULT_MODELS["anthropic"]      # compatibilidad con codigo anterior

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


def _read_values():
    values = {}
    path = paths.ENV_PATH
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                values = parse_env(f.read())
        except OSError:
            values = {}
    return values


def _get(values, var):
    return (values.get(var) or os.environ.get(var) or "").strip()


def active_provider(values=None):
    """Proveedor activo (AI_PROVIDER); si falta o no es valido, el por defecto."""
    values = _read_values() if values is None else values
    p = _get(values, PROVIDER_VAR).lower()
    return p if p in PROVIDERS else DEFAULT_PROVIDER


def read_settings():
    """
    {"provider", "providers": {nombre: {"api_key","model","has_key"}}, y, para el proveedor
    ACTIVO, los atajos "api_key", "model", "has_key"}.
    """
    values = _read_values()
    provider = active_provider(values)
    per = {}
    for p in PROVIDERS:
        key = _get(values, KEY_VARS[p])
        model = _get(values, MODEL_VARS[p]) or DEFAULT_MODELS[p]
        per[p] = {"api_key": key, "model": model, "has_key": bool(key)}
    out = {"provider": provider, "providers": per}
    out.update(per[provider])
    return out


def mask_key(key):
    """Version no reversible para mostrar: primeros 7 y ultimos 4 caracteres."""
    key = key or ""
    if len(key) <= 10:
        return "*" * len(key)
    return key[:7] + "..." + key[-4:]


def validate(api_key, model, provider=None):
    """Lanza PTError (sin incluir la key en el mensaje) si algo no es valido."""
    provider = normalize_provider(provider) if provider else active_provider()
    name = LABELS[provider]
    if not (api_key or "").strip():
        raise PTError(f"escribe la API key de {name}.")
    if re.search(r"\s", api_key.strip()):
        raise PTError("la API key no puede contener espacios ni saltos de linea.")
    if not (model or "").strip():
        ejemplo = (f" (por ejemplo {DEFAULT_MODELS[provider]})" if DEFAULT_MODELS[provider]
                   else " (un modelo con vision)")
        raise PTError(f"escribe el modelo de {name}{ejemplo}.")
    if re.search(r"[^A-Za-z0-9._:\-]", model.strip()):
        raise PTError("el modelo solo puede tener letras, numeros y . _ : -")


def save_settings(api_key, model, provider=None):
    """
    Guarda AI_PROVIDER y la clave/modelo de ESE proveedor en .env (provider=None: el activo).
    Devuelve la ruta del archivo.
    """
    provider = normalize_provider(provider) if provider else active_provider()
    validate(api_key, model, provider)
    api_key, model = api_key.strip(), model.strip()
    path = paths.ENV_PATH
    lines = []
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError as e:
            raise PTError(f"no se pudo leer {path}: {type(e).__name__}") from e
    wanted = {PROVIDER_VAR: provider, KEY_VARS[provider]: api_key, MODEL_VARS[provider]: model}
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
    for var, val in wanted.items():
        os.environ[var] = val
    return path
