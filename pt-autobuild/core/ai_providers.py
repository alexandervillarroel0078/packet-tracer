"""
core.ai_providers - proveedores de IA con vision para la autocalibracion (OpenAI y Anthropic).

Interfaz comun, una implementacion por proveedor, sin SDK (solo urllib):

    send(cfg, prompt, image_b64=None)  ->  texto de la respuesta (el JSON pedido)

Cada proveedor tiene tres piezas puras y testeables sin red:
    build_request(cfg, prompt, image_b64, max_tokens)  -> (url, headers, body_bytes)
    parse_response(provider, payload)                  -> texto
    map_error(provider, status, payload, model)        -> mensaje claro (ya con el nombre del
                                                          proveedor y la variable a revisar)

NUNCA se imprime ni se incluye una clave en un mensaje: todo texto que pueda contenerla pasa
por redact(), que cubre las claves de ambos proveedores (por valor exacto y por patron).
"""

import json
import re
import urllib.error
import urllib.request
from typing import NamedTuple

from core.errors import AutoCalibrateError

PROVIDERS = ("openai", "anthropic")
DEFAULT_PROVIDER = "openai"
LABELS = {"openai": "OpenAI", "anthropic": "Anthropic"}
KEY_VARS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
MODEL_VARS = {"openai": "OPENAI_MODEL", "anthropic": "ANTHROPIC_MODEL"}
# OpenAI: sin modelo por defecto (se configura; hay que elegir uno con vision).
DEFAULT_MODELS = {"openai": "", "anthropic": "claude-sonnet-5-5"}
KEY_URLS = {"openai": "https://platform.openai.com/api-keys",
            "anthropic": "https://console.anthropic.com/settings/keys"}

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
TIMEOUT = 90


class AIConfig(NamedTuple):
    provider: str
    key: str
    model: str


def normalize_provider(name):
    """'OpenAI ' -> 'openai'. AutoCalibrateError si no es uno de PROVIDERS."""
    p = (name or "").strip().lower()
    if p not in PROVIDERS:
        raise AutoCalibrateError(
            f"proveedor de IA desconocido: '{name}'. Validos: {', '.join(PROVIDERS)} "
            "(AI_PROVIDER en .env o el selector de Ajustes).")
    return p


def label(provider):
    return LABELS.get(provider, provider)


# =====================================================================
# Claves: nunca se muestran
# =====================================================================
_KEY_PATTERNS = (
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "sk-ant-***"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
)


def redact(text, *keys):
    """Quita de `text` las claves dadas (valor exacto) y cualquier cosa con forma de clave de
    OpenAI (sk-...), Anthropic (sk-ant-...) o cabecera 'Bearer ...'."""
    text = str(text)
    for key in keys:
        if key and len(key) >= 4:
            text = text.replace(key, "***")
    for pat, repl in _KEY_PATTERNS:
        text = pat.sub(repl, text)
    return text


# =====================================================================
# Construccion de peticiones (puro)
# =====================================================================
def build_request(cfg, prompt, image_b64=None, max_tokens=1024):
    """-> (url, headers, body_bytes). `headers` lleva la clave: no registrarlos jamas."""
    provider = normalize_provider(cfg.provider)
    if provider == "openai":
        content = [{"type": "text", "text": prompt}]
        if image_b64:
            content.append({"type": "image_url", "image_url": {
                "url": f"data:image/png;base64,{image_b64}", "detail": "high"}})
        body = {"model": cfg.model,
                "messages": [{"role": "user", "content": content}],
                "response_format": {"type": "json_object"}}
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {cfg.key}"}
        return OPENAI_URL, headers, json.dumps(body).encode("utf-8")
    content = []
    if image_b64:
        content.append({"type": "image", "source": {"type": "base64",
                                                    "media_type": "image/png",
                                                    "data": image_b64}})
    content.append({"type": "text", "text": prompt})
    body = {"model": cfg.model, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}
    headers = {"content-type": "application/json", "x-api-key": cfg.key,
               "anthropic-version": ANTHROPIC_VERSION}
    return ANTHROPIC_URL, headers, json.dumps(body).encode("utf-8")


# =====================================================================
# Respuestas (puro)
# =====================================================================
def parse_response(provider, payload):
    """Texto de la respuesta (el JSON pedido). AutoCalibrateError si viene vacia o rechazada."""
    provider = normalize_provider(provider)
    name = label(provider)
    if not isinstance(payload, dict):
        raise AutoCalibrateError(f"respuesta inesperada de {name}.")
    if provider == "anthropic":
        texts = [b.get("text", "") for b in payload.get("content", []) or []
                 if isinstance(b, dict) and b.get("type") == "text"]
        if not any(t.strip() for t in texts):
            raise AutoCalibrateError("la API de Anthropic devolvio una respuesta sin texto.")
        return "\n".join(texts)

    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise AutoCalibrateError("OpenAI devolvio una respuesta sin 'choices'.")
    choice = choices[0]
    message = choice.get("message") or {}
    if message.get("refusal"):
        raise AutoCalibrateError(f"OpenAI se nego a responder: {message['refusal']}")
    content = message.get("content")
    if isinstance(content, list):          # partes de contenido
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        if choice.get("finish_reason") == "length":
            raise AutoCalibrateError("OpenAI corto la respuesta por longitud (sin texto util).")
        if choice.get("finish_reason") == "content_filter":
            raise AutoCalibrateError("OpenAI filtro la respuesta (content_filter).")
        raise AutoCalibrateError("OpenAI devolvio una respuesta sin texto.")
    return content


# =====================================================================
# Errores HTTP -> mensajes claros (puro)
# =====================================================================
def _err_fields(payload):
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, str):
        return "", "", err
    err = err if isinstance(err, dict) else {}
    return str(err.get("code") or ""), str(err.get("type") or ""), str(err.get("message") or "")


def map_error(provider, status, payload, model):
    """Mensaje claro para un error HTTP de la API (sin clave; el llamador ademas redacta)."""
    provider = normalize_provider(provider)
    code, typ, msg = _err_fields(payload)
    kv, mv, name = KEY_VARS[provider], MODEL_VARS[provider], label(provider)
    low = f"{code} {typ} {msg}".lower()

    if status in (401,) or code == "invalid_api_key" or typ == "authentication_error":
        return f"{name} rechazo la clave (HTTP {status}). Revisa {kv} en Ajustes."
    if "insufficient_quota" in low or "credit balance" in low or "billing" in low:
        return (f"Sin saldo o cuota en tu cuenta de {name}: revisa la facturacion y los limites "
                f"del proyecto. (HTTP {status})")
    if status == 429:
        return (f"Limite de uso de {name} (HTTP 429): demasiadas peticiones o tokens por minuto. "
                "Reintenta en unos minutos.")
    if status == 404 or code == "model_not_found" or typ == "not_found_error":
        return (f"El modelo '{model}' no existe o tu cuenta de {name} no tiene acceso. "
                f"Revisa {mv} en Ajustes (debe ser un modelo con vision).")
    if status == 403:
        return (f"{name} denego el acceso (HTTP 403): permisos de la clave/proyecto o region no "
                f"soportada. {msg}".strip())
    if status == 400 and any(w in low for w in ("image", "vision", "multimodal")):
        return (f"El modelo '{model}' rechazo la imagen; puede que no admita vision. "
                f"Elige otro en {mv}. Detalle: {msg}")
    if status >= 500 or status == 529 or "overloaded" in low:
        return f"El servicio de {name} no esta disponible ahora (HTTP {status}). Reintenta mas tarde."
    return f"error de {name} (HTTP {status}): {msg or 'sin detalle'}"


# =====================================================================
# HTTP (el unico punto con red)
# =====================================================================
def send(cfg, prompt, image_b64=None, max_tokens=1024, opener=None, timeout=TIMEOUT):
    """
    Envia la peticion al proveedor de `cfg` y devuelve el texto de la respuesta.
    `opener` (def. urllib.request.urlopen) permite simular la red en pruebas.
    Lanza AutoCalibrateError con causa clara; ningun mensaje contiene la clave.
    """
    provider = normalize_provider(cfg.provider)
    name = label(provider)
    url, headers, body = build_request(cfg, prompt, image_b64, max_tokens)
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    opener = opener or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_payload = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            err_payload = {}
        raise AutoCalibrateError(redact(map_error(provider, e.code, err_payload, cfg.model),
                                        cfg.key)) from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise AutoCalibrateError(
                f"{name} no respondio a tiempo (timeout). Reintenta.") from None
        raise AutoCalibrateError(redact(
            f"sin conexion con la API de {name} ({e.reason}). Comprueba tu red / proxy.",
            cfg.key)) from None
    except TimeoutError:
        raise AutoCalibrateError(f"{name} no respondio a tiempo (timeout). Reintenta.") from None
    except (OSError, ValueError) as e:
        raise AutoCalibrateError(redact(
            f"respuesta de red invalida de {name}: {type(e).__name__}", cfg.key)) from None
    return parse_response(provider, payload)
