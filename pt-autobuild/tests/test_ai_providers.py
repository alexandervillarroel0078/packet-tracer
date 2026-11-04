"""
Proveedores de IA (OpenAI / Anthropic) con la RED SIMULADA: ninguna prueba llama a una API.

Se comprueba: seleccion de proveedor, construccion de la peticion de cada uno, parseo de las
respuestas, mapeo de errores a mensajes claros, rechazo de coordenadas normalizadas, cache por
proveedor+modelo, y que NINGUNA clave aparezca en logs, mensajes ni excepciones.
"""

import io
import json
import os
import urllib.error

import pytest

from core import ai_providers as ap
from core import autocalibrate as ac
from core import paths, settings
from core.ai_providers import AIConfig
from core.errors import AutoCalibrateError
from panel.controllers import Shared
from panel.controllers.ajustes import AjustesController
from panel.controllers.runner import ActionRunner

OPENAI_KEY = "sk-proj-AbCdEf0123456789SECRETOopenai"
ANTHROPIC_KEY = "sk-ant-api03-ZyXwVu9876543210SECRETOanthropic"
OAI = AIConfig("openai", OPENAI_KEY, "modelo-vision-x")
ANT = AIConfig("anthropic", ANTHROPIC_KEY, "claude-sonnet-5-5")
IMG = "QUJDREVGRw=="           # base64 cualquiera


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(status, payload):
    body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
    return urllib.error.HTTPError("https://x", status, "err", {}, io.BytesIO(body))


def opener_returning(payload):
    calls = []

    def opener(req, timeout=None):
        calls.append(req)
        return FakeResp(payload)
    opener.calls = calls
    return opener


def opener_raising(exc):
    def opener(req, timeout=None):
        raise exc
    return opener


OPENAI_OK = {"choices": [{"message": {"content": '{"search_field": {"x": 100, "y": 200}}'},
                          "finish_reason": "stop"}]}
ANTHROPIC_OK = {"content": [{"type": "text", "text": '{"search_field": {"x": 100, "y": 200}}'}]}


# =====================================================================
# Seleccion de proveedor (.env / entorno)
# =====================================================================
def test_proveedor_por_defecto_es_openai(isolated_data_dir):
    s = settings.read_settings()
    assert s["provider"] == "openai" and settings.active_provider() == "openai"
    assert s["providers"]["openai"]["model"] == ""              # sin modelo hardcodeado
    assert s["providers"]["anthropic"]["model"] == "claude-sonnet-5-5"


def test_proveedor_desde_env_y_desde_entorno(isolated_data_dir, monkeypatch):
    with open(paths.ENV_PATH, "w", encoding="utf-8") as f:
        f.write("AI_PROVIDER=anthropic\nANTHROPIC_API_KEY=k1\nOPENAI_API_KEY=k2\n"
                "OPENAI_MODEL=m2\n")
    s = settings.read_settings()
    assert s["provider"] == "anthropic" and s["api_key"] == "k1"        # atajos = activo
    assert s["providers"]["openai"]["api_key"] == "k2"
    assert s["providers"]["openai"]["model"] == "m2"
    monkeypatch.setenv("AI_PROVIDER", "openai")                          # el .env manda
    assert settings.active_provider() == "anthropic"
    os.remove(paths.ENV_PATH)
    assert settings.active_provider() == "openai"                        # entorno
    monkeypatch.setenv("AI_PROVIDER", "Nada")
    assert settings.active_provider() == "openai"                        # invalido -> defecto


def test_load_config_usa_el_proveedor_activo(isolated_data_dir):
    settings.save_settings(OPENAI_KEY, "modelo-vision-x", "openai")
    settings.save_settings(ANTHROPIC_KEY, "claude-sonnet-5-5", "anthropic")
    assert ac.load_config() == AIConfig("anthropic", ANTHROPIC_KEY, "claude-sonnet-5-5")
    settings.save_settings(OPENAI_KEY, "modelo-vision-x", "openai")      # vuelve a openai
    assert ac.load_config() == AIConfig("openai", OPENAI_KEY, "modelo-vision-x")


def test_load_config_errores_claros_sin_la_clave(isolated_data_dir):
    with pytest.raises(AutoCalibrateError) as ei:
        ac.load_config()                                                  # nada configurado
    assert "OPENAI_API_KEY" in str(ei.value) and "Ajustes" in str(ei.value)
    settings.save_settings(OPENAI_KEY, "m", "openai")
    with open(paths.ENV_PATH, encoding="utf-8") as f:
        text = f.read().replace("OPENAI_MODEL=m", "OPENAI_MODEL=")
    with open(paths.ENV_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    os.environ["OPENAI_MODEL"] = ""
    with pytest.raises(AutoCalibrateError) as ei:
        ac.load_config()
    assert "OPENAI_MODEL" in str(ei.value) and OPENAI_KEY not in str(ei.value)


def test_proveedor_invalido():
    with pytest.raises(AutoCalibrateError):
        ap.normalize_provider("gemini")
    assert ap.normalize_provider(" OpenAI ") == "openai"


def test_guardar_conserva_el_otro_proveedor(isolated_data_dir):
    settings.save_settings(OPENAI_KEY, "m-openai", "openai")
    settings.save_settings(ANTHROPIC_KEY, "m-anthropic", "anthropic")
    text = open(paths.ENV_PATH, encoding="utf-8").read()
    for line in (f"OPENAI_API_KEY={OPENAI_KEY}", "OPENAI_MODEL=m-openai",
                 f"ANTHROPIC_API_KEY={ANTHROPIC_KEY}", "ANTHROPIC_MODEL=m-anthropic",
                 "AI_PROVIDER=anthropic"):
        assert line in text
    assert text.count("AI_PROVIDER=") == 1


def test_validar_ajustes_por_proveedor(isolated_data_dir):
    with pytest.raises(Exception) as ei:
        settings.validate("k", "", "openai")
    assert "OpenAI" in str(ei.value)
    with pytest.raises(Exception) as ei:
        settings.validate("", "m", "anthropic")
    assert "Anthropic" in str(ei.value)
    settings.validate("k", "m", "openai")


# =====================================================================
# Construccion de la peticion
# =====================================================================
def test_peticion_openai():
    url, headers, body = ap.build_request(OAI, "dame JSON", IMG)
    data = json.loads(body)
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers["Authorization"] == f"Bearer {OPENAI_KEY}"
    assert "x-api-key" not in headers
    assert data["model"] == "modelo-vision-x"
    assert data["response_format"] == {"type": "json_object"}
    parts = data["messages"][0]["content"]
    assert {"type": "text", "text": "dame JSON"} in parts
    img = next(p for p in parts if p["type"] == "image_url")
    assert img["image_url"]["url"] == f"data:image/png;base64,{IMG}"
    assert OPENAI_KEY not in body.decode("utf-8")          # la clave solo va en la cabecera


def test_peticion_openai_solo_texto():
    _url, _h, body = ap.build_request(OAI, "hola JSON", None)
    parts = json.loads(body)["messages"][0]["content"]
    assert [p["type"] for p in parts] == ["text"]


def test_peticion_anthropic():
    url, headers, body = ap.build_request(ANT, "dame JSON", IMG, max_tokens=77)
    data = json.loads(body)
    assert url == "https://api.anthropic.com/v1/messages"
    assert headers["x-api-key"] == ANTHROPIC_KEY and "anthropic-version" in headers
    assert "Authorization" not in headers
    assert data["model"] == "claude-sonnet-5-5" and data["max_tokens"] == 77
    assert "response_format" not in data
    blocks = data["messages"][0]["content"]
    assert blocks[0] == {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                     "data": IMG}}
    assert blocks[1] == {"type": "text", "text": "dame JSON"}


def test_send_usa_el_proveedor_de_la_config():
    op = opener_returning(OPENAI_OK)
    ap.send(OAI, "p JSON", IMG, opener=op)
    assert op.calls[0].full_url.startswith("https://api.openai.com")
    op = opener_returning(ANTHROPIC_OK)
    ap.send(ANT, "p", IMG, opener=op)
    assert op.calls[0].full_url.startswith("https://api.anthropic.com")


# =====================================================================
# Parseo de respuestas
# =====================================================================
def test_parseo_openai():
    assert json.loads(ap.parse_response("openai", OPENAI_OK))["search_field"]["x"] == 100
    parts = {"choices": [{"message": {"content": [{"type": "text", "text": "{"},
                                                  {"type": "text", "text": "}"}]}}]}
    assert ap.parse_response("openai", parts) == "{}"


@pytest.mark.parametrize("payload,frag", [
    ({}, "choices"),
    ({"choices": []}, "choices"),
    ({"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}, "sin texto"),
    ({"choices": [{"message": {"content": None}, "finish_reason": "length"}]}, "longitud"),
    ({"choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}]}, "filtro"),
    ({"choices": [{"message": {"refusal": "no puedo", "content": None}}]}, "se nego"),
    ([], "inesperada"),
])
def test_parseo_openai_invalido(payload, frag):
    with pytest.raises(AutoCalibrateError) as ei:
        ap.parse_response("openai", payload)
    assert frag in str(ei.value)


def test_parseo_anthropic():
    assert "search_field" in ap.parse_response("anthropic", ANTHROPIC_OK)
    two = {"content": [{"type": "text", "text": "a"}, {"type": "tool_use"},
                       {"type": "text", "text": "b"}]}
    assert ap.parse_response("anthropic", two) == "a\nb"
    with pytest.raises(AutoCalibrateError):
        ap.parse_response("anthropic", {"content": []})


# =====================================================================
# Mapeo de errores
# =====================================================================
@pytest.mark.parametrize("status,payload,frag", [
    (401, {"error": {"code": "invalid_api_key", "message": "Incorrect API key provided"}},
     "rechazo la clave"),
    (429, {"error": {"code": "insufficient_quota", "type": "insufficient_quota",
                     "message": "You exceeded your current quota"}}, "Sin saldo o cuota"),
    (429, {"error": {"code": "rate_limit_exceeded", "message": "Rate limit reached"}},
     "Limite de uso"),
    (404, {"error": {"code": "model_not_found", "message": "The model does not exist"}},
     "no existe"),
    (403, {"error": {"message": "Country, region, or territory not supported"}}, "denego"),
    (400, {"error": {"message": "image_url is not supported by this model"}}, "vision"),
    (500, {"error": {"message": "server error"}}, "no esta disponible"),
    (503, {}, "no esta disponible"),
    (418, {"error": {"message": "soy una tetera"}}, "HTTP 418"),
])
def test_errores_openai(status, payload, frag):
    msg = ap.map_error("openai", status, payload, "modelo-vision-x")
    assert frag in msg
    if status == 401:
        assert "OPENAI_API_KEY" in msg
    if status == 404:
        assert "modelo-vision-x" in msg and "OPENAI_MODEL" in msg


@pytest.mark.parametrize("status,payload,frag", [
    (401, {"error": {"type": "authentication_error", "message": "invalid x-api-key"}},
     "rechazo la clave"),
    (400, {"error": {"type": "invalid_request_error",
                     "message": "Your credit balance is too low"}}, "Sin saldo o cuota"),
    (429, {"error": {"type": "rate_limit_error", "message": "x"}}, "Limite de uso"),
    (404, {"error": {"type": "not_found_error", "message": "model: x"}}, "no existe"),
    (529, {"error": {"type": "overloaded_error", "message": "Overloaded"}}, "no esta disponible"),
])
def test_errores_anthropic(status, payload, frag):
    msg = ap.map_error("anthropic", status, payload, "claude-sonnet-5-5")
    assert frag in msg and "Anthropic" in msg


def test_send_mapea_http_a_autocalibrateerror():
    op = opener_raising(http_error(401, {"error": {"code": "invalid_api_key"}}))
    with pytest.raises(AutoCalibrateError) as ei:
        ap.send(OAI, "p", IMG, opener=op)
    assert "rechazo la clave" in str(ei.value)
    op = opener_raising(http_error(429, {"error": {"code": "insufficient_quota"}}))
    with pytest.raises(AutoCalibrateError) as ei:
        ap.send(OAI, "p", IMG, opener=op)
    assert "Sin saldo" in str(ei.value)


def test_send_errores_de_red_y_timeout():
    with pytest.raises(AutoCalibrateError) as ei:
        ap.send(OAI, "p", opener=opener_raising(urllib.error.URLError("getaddrinfo failed")))
    assert "sin conexion" in str(ei.value) and "OpenAI" in str(ei.value)
    with pytest.raises(AutoCalibrateError) as ei:
        ap.send(ANT, "p", opener=opener_raising(urllib.error.URLError(TimeoutError("t"))))
    assert "timeout" in str(ei.value) and "Anthropic" in str(ei.value)
    with pytest.raises(AutoCalibrateError) as ei:
        ap.send(OAI, "p", opener=opener_raising(TimeoutError()))
    assert "timeout" in str(ei.value)


def test_send_respuesta_no_json():
    with pytest.raises(AutoCalibrateError) as ei:
        ap.send(OAI, "p", opener=opener_returning(b"<html>no json</html>"))
    assert "invalida" in str(ei.value)


# =====================================================================
# Las claves NUNCA aparecen
# =====================================================================
def test_redact_cubre_ambos_proveedores():
    text = (f"fallo con {OPENAI_KEY} y {ANTHROPIC_KEY} y Authorization: Bearer abc.DEF-123 "
            "y una clave rara qwerty-9999-zzzz")
    out = ap.redact(text, "qwerty-9999-zzzz")
    for secret in (OPENAI_KEY, ANTHROPIC_KEY, "abc.DEF-123", "qwerty-9999-zzzz"):
        assert secret not in out
    assert "sk-ant-***" in out and "sk-***" in out and "Bearer ***" in out
    assert ac.redact(text, OPENAI_KEY).count(OPENAI_KEY) == 0           # alias de autocalibrate


@pytest.mark.parametrize("cfg", [OAI, ANT])
def test_el_mensaje_de_la_api_que_repite_la_clave_se_redacta(cfg):
    echo = {"error": {"code": "invalid_api_key", "type": "authentication_error",
                      "message": f"Incorrect API key provided: {cfg.key}. See docs"}}
    for status in (401, 400, 403, 418):
        op = opener_raising(http_error(status, echo))
        with pytest.raises(AutoCalibrateError) as ei:
            ap.send(cfg, "p", IMG, opener=op)
        e = ei.value
        assert cfg.key not in str(e) and cfg.key not in repr(e)
        assert e.__cause__ is None


def test_la_clave_no_esta_en_el_error_de_red():
    exc = urllib.error.URLError(f"fallo con {OPENAI_KEY}")
    with pytest.raises(AutoCalibrateError) as ei:
        ap.send(OAI, "p", opener=opener_raising(exc))
    assert OPENAI_KEY not in str(ei.value) and ei.value.__cause__ is None


# =====================================================================
# Coordenadas normalizadas / fuera de rango
# =====================================================================
def test_coordenadas_normalizadas_se_rechazan_con_mensaje_claro():
    text = json.dumps({"search_field": {"x": 0.12, "y": 0.93},
                       "canvas_top_left": {"x": 0.02, "y": 0.1},
                       "canvas_bottom_right": [0.9, 0.7]})
    pts, warns = ac.parse_ai_response(text, (1568, 882))
    assert pts == {}
    joined = "\n".join(warns)
    assert "NORMALIZADA" in joined and "rechazada" in joined
    assert "coordenadas normalizadas" in joined             # resumen
    assert "1568x882" in joined


def test_fuera_de_rango_se_rechaza_y_los_validos_se_conservan():
    text = json.dumps({"search_field": {"x": 150, "y": 800},
                       "canvas_top_left": {"x": 5000, "y": 100},
                       "canvas_bottom_right": {"x": 1200, "y": -3}})
    pts, warns = ac.parse_ai_response(text, (1568, 882))
    assert pts == {"search_field": (150, 800)}
    assert sum("fuera de la imagen" in w and "rechazada" in w for w in warns) == 2


def test_normalizadas_en_la_respuesta_con_estados():
    text = json.dumps({"states": {"main": True},
                       "points": {"search_field": {"x": 0.1, "y": 0.9}}})
    pts, states, warns = ac.parse_multi_response(text, (1000, 800), ["search_field"], ["main"])
    assert pts == {} and states == {"main": True}
    assert any("NORMALIZADA" in w for w in warns)


def test_un_pixel_real_cerca_del_origen_no_se_confunde():
    pts, _ = ac.parse_ai_response('{"search_field": {"x": 5, "y": 2}}', (100, 100),
                                  ("search_field",))
    assert pts == {"search_field": (5, 2)}


# =====================================================================
# Cache por proveedor + modelo
# =====================================================================
ENV = {"resolution": [1920, 1080], "dpi_scale": 1.0, "window": [0, 0, 1920, 1040]}


def _meta(provider="openai", model="m1"):
    el = {"status": "ok", "point": [1, 2], "template": "auto_x.png"}
    return {"version": ac.META_VERSION, "resolution": [1920, 1080], "dpi_scale": 1.0,
            "window": [0, 0, 1920, 1040], "provider": provider, "model": model,
            "elements": {n: dict(el) for n in ac.REQUIRED}}


def test_cache_incluye_proveedor_y_modelo():
    env = dict(ENV, provider="openai", model="m1")
    assert ac.cache_decision(_meta(), env)[0] is True
    ok, why = ac.cache_decision(_meta(provider="anthropic"), env)
    assert not ok and "proveedor/modelo" in why
    ok, why = ac.cache_decision(_meta(model="m2"), env)
    assert not ok and "proveedor/modelo" in why
    old = _meta()
    del old["provider"]                                  # calibracion anterior a los proveedores
    assert ac.cache_decision(old, env)[0] is False
    assert ac.cache_decision(_meta(provider="anthropic"), ENV)[0] is True   # sin proveedor en env


# =====================================================================
# Extremo a extremo con red simulada
# =====================================================================
def test_ajustes_probar_conexion_openai_registra_proveedor_y_modelo_sin_clave(
        isolated_data_dir, monkeypatch):
    shared = Shared(ActionRunner(sync=True))
    op = opener_returning({"choices": [{"message": {"content": '{"ok": true}'}}]})
    monkeypatch.setattr("urllib.request.urlopen", op)
    AjustesController(shared).test_connection(OPENAI_KEY, "modelo-vision-x", "openai")
    out = "\n".join(e[1] for e in shared.runner.drain() if e[0] == "log")
    assert "Proveedor: OpenAI" in out and "modelo-vision-x" in out
    assert "Conexion correcta con OpenAI" in out and OPENAI_KEY not in out
    assert op.calls[0].full_url.startswith("https://api.openai.com")
    assert op.calls[0].headers["Authorization"] == f"Bearer {OPENAI_KEY}"


def test_ajustes_probar_conexion_anthropic(isolated_data_dir, monkeypatch):
    shared = Shared(ActionRunner(sync=True))
    op = opener_returning(ANTHROPIC_OK)
    monkeypatch.setattr("urllib.request.urlopen", op)
    AjustesController(shared).test_connection(ANTHROPIC_KEY, "claude-sonnet-5-5", "anthropic")
    out = "\n".join(e[1] for e in shared.runner.drain() if e[0] == "log")
    assert "Proveedor: Anthropic" in out and "Conexion correcta con Anthropic" in out
    assert ANTHROPIC_KEY not in out
    assert op.calls[0].full_url.startswith("https://api.anthropic.com")


@pytest.mark.parametrize("cfg", [OAI, ANT])
def test_ajustes_error_de_api_no_filtra_la_clave_al_log(isolated_data_dir, monkeypatch, cfg):
    shared = Shared(ActionRunner(sync=True))
    echo = {"error": {"code": "invalid_api_key", "type": "authentication_error",
                      "message": f"bad key {cfg.key}"}}
    monkeypatch.setattr("urllib.request.urlopen", opener_raising(http_error(401, echo)))
    AjustesController(shared).test_connection(cfg.key, cfg.model, cfg.provider)
    out = "\n".join(e[1] for e in shared.runner.drain() if e[0] == "log")
    assert "[ERROR]" in out and "rechazo la clave" in out and cfg.key not in out


def test_ajustes_guardar_mensaje_dice_proveedor_sin_la_clave(isolated_data_dir):
    msg = AjustesController(Shared(ActionRunner(sync=True))).save(
        OPENAI_KEY, "modelo-vision-x", "openai")
    assert "OpenAI" in msg and "modelo-vision-x" in msg and OPENAI_KEY not in msg


def test_autocalibrar_dry_run_loguea_proveedor_y_modelo_y_rechaza_normalizadas(
        isolated_data_dir, monkeypatch):
    """run_autocalibrate completo (dry-run): la IA simulada devuelve coordenadas normalizadas."""
    settings.save_settings(OPENAI_KEY, "modelo-vision-x", "openai")
    reply = {"choices": [{"message": {"content": json.dumps({
        "states": {"main": True},
        "points": {"search_field": {"x": 0.1, "y": 0.9},
                   "canvas_top_left": {"x": 0.05, "y": 0.1},
                   "canvas_bottom_right": [0.8, 0.7], "cable_icon": {"x": 0.2, "y": 0.9}}})}}]}
    op = opener_returning(reply)
    monkeypatch.setattr("urllib.request.urlopen", op)
    lines = []
    try:
        code = ac.run_autocalibrate(dry_run=True, groups=("main",), log=lines.append)
    except Exception as e:   # sin pantalla no se puede capturar
        pytest.skip(f"sin captura de pantalla disponible: {e}")
    out = "\n".join(lines)
    assert code == 1                                          # nada quedo calibrado
    assert "Proveedor: OpenAI   Modelo: modelo-vision-x" in out
    assert "NORMALIZADA" in out and "rechazada" in out
    assert OPENAI_KEY not in out
    assert len(op.calls) == 1 and op.calls[0].full_url.startswith("https://api.openai.com")
    assert not os.path.exists(paths.COORDS_PATH)             # dry-run: no se guardo nada
