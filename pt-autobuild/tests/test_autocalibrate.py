"""Pruebas de la logica pura de core.autocalibrate (sin pantalla, red ni API)."""
import json

import pytest

from core import autocalibrate as ac

NAMES = tuple(ac.ELEMENTS)


# --- conversion de coordenadas -----------------------------------------
def test_compute_send_size_no_amplia():
    assert ac.compute_send_size(1000, 600) == (1000, 600)


def test_compute_send_size_reduce_manteniendo_proporcion():
    assert ac.compute_send_size(3136, 1568) == (1568, 784)


def test_image_to_screen_sin_redimensionar():
    upp = ac.compute_units_per_px((1000, 500), (1000, 500), 1.0)
    assert ac.image_to_screen(100, 50, (200, 300), upp) == (300, 350)


def test_image_to_screen_con_redimensionado():
    # ventana 3000x1500 enviada a 1500x750 -> cada px enviado = 2 px de pantalla
    upp = ac.compute_units_per_px((3000, 1500), (1500, 750), 1.0)
    assert ac.image_to_screen(500, 100, (10, 20), upp) == (1010, 220)


def test_image_to_screen_con_escala_dpi():
    # proceso no DPI aware al 125 %: captura 1.25 px por unidad de pantalla
    upp = ac.compute_units_per_px((2500, 1250), (2500, 1250), 1.25)
    assert ac.image_to_screen(1250, 625, (0, 0), upp) == (1000, 500)


def test_image_to_screen_redimensionado_y_dpi():
    upp = ac.compute_units_per_px((3000, 1500), (1500, 750), 1.5)
    assert ac.image_to_screen(750, 375, (100, 50), upp) == (1100, 550)


def test_compute_units_per_px_valida():
    with pytest.raises(ValueError):
        ac.compute_units_per_px((0, 10), (10, 10), 1.0)
    with pytest.raises(ValueError):
        ac.compute_units_per_px((10, 10), (10, 10), 0)


# --- parseo / validacion del JSON de la IA -----------------------------
GOOD = {"search_field": {"x": 100, "y": 700}, "filtered_result": None,
        "canvas_top_left": {"x": 20, "y": 120}, "canvas_bottom_right": [900, 600]}


def test_parse_json_limpio():
    pts, warns = ac.parse_ai_response(json.dumps(GOOD), (1000, 800), NAMES)
    assert pts == {"search_field": (100, 700), "canvas_top_left": (20, 120),
                   "canvas_bottom_right": (900, 600)}
    assert any("filtered_result" in w for w in warns)


def test_parse_con_markdown_y_texto():
    text = "Aqui tienes:\n```json\n" + json.dumps(GOOD) + "\n```\nListo."
    pts, _ = ac.parse_ai_response(text, (1000, 800), NAMES)
    assert pts["search_field"] == (100, 700)


def test_parse_con_texto_sin_fences():
    pts, _ = ac.parse_ai_response("ok " + json.dumps(GOOD) + " fin", (1000, 800), NAMES)
    assert len(pts) == 3


def test_parse_redondea_flotantes():
    pts, _ = ac.parse_ai_response('{"search_field": {"x": 10.6, "y": 20.4}}',
                                  (100, 100), ("search_field",))
    assert pts["search_field"] == (11, 20)


@pytest.mark.parametrize("bad", ["no hay json", "{roto", "[1, 2]", ""])
def test_parse_invalido_lanza(bad):
    with pytest.raises(ac.AutoCalibrateError):
        ac.parse_ai_response(bad, (100, 100), NAMES)


def test_parse_descarta_fuera_de_imagen_y_formatos_malos():
    raw = {"search_field": {"x": 5000, "y": 10}, "filtered_result": "aqui",
           "canvas_top_left": {"x": -1, "y": 5}, "canvas_bottom_right": [True, 3]}
    pts, warns = ac.parse_ai_response(json.dumps(raw), (1000, 800), NAMES)
    assert pts == {}
    assert len(warns) == 4


def test_parse_lienzo_incoherente_se_descarta():
    raw = {"canvas_top_left": [500, 500], "canvas_bottom_right": [510, 510]}
    pts, warns = ac.parse_ai_response(json.dumps(raw), (1000, 800), NAMES)
    assert "canvas_top_left" not in pts and "canvas_bottom_right" not in pts
    assert any("lienzo" in w for w in warns)


# --- decision de cache --------------------------------------------------
ENV = {"resolution": [1920, 1080], "dpi_scale": 1.25, "window": [0, 0, 1920, 1040]}


def _meta(**over):
    el = {"status": "ok", "point": [1, 2], "template": "auto_x.png"}
    m = {"version": ac.META_VERSION, "resolution": [1920, 1080], "dpi_scale": 1.25,
         "window": [0, 0, 1920, 1040], "elements": {n: dict(el) for n in ac.REQUIRED}}
    m.update(over)
    return m


def test_cache_valida():
    assert ac.cache_decision(_meta(), ENV)[0] is True


def test_cache_sin_meta():
    assert ac.cache_decision(None, ENV)[0] is False
    assert ac.cache_decision({}, ENV)[0] is False


def test_cache_cambia_resolucion():
    ok, why = ac.cache_decision(_meta(resolution=[1366, 768]), ENV)
    assert not ok and "resolucion" in why


def test_cache_cambia_dpi():
    ok, why = ac.cache_decision(_meta(dpi_scale=1.0), ENV)
    assert not ok and "DPI" in why


def test_cache_ventana_movida_vs_tolerancia():
    assert not ac.cache_decision(_meta(window=[40, 0, 1920, 1040]), ENV)[0]
    assert ac.cache_decision(_meta(window=[1, 0, 1920, 1040]), ENV)[0]


def test_cache_elemento_requerido_no_ok():
    m = _meta()
    m["elements"]["search_field"]["status"] = "manual"
    ok, why = ac.cache_decision(m, ENV)
    assert not ok and "search_field" in why


def test_cache_filtered_result_opcional():
    m = _meta()
    m["elements"]["filtered_result"] = {"status": "manual"}
    assert ac.cache_decision(m, ENV)[0] is True


def test_cache_version_distinta():
    assert not ac.cache_decision(_meta(version=999), ENV)[0]


# --- evaluacion de coincidencia / redaccion de la key ------------------
def test_evaluate_match():
    assert ac.evaluate_match(0.97, (10, 10), (12, 11))
    assert not ac.evaluate_match(0.50, (10, 10), (10, 10))
    assert not ac.evaluate_match(0.99, (10, 10), (60, 10))
    assert not ac.evaluate_match(float("nan"), (0, 0), (0, 0))
    assert not ac.evaluate_match(None, (0, 0), (0, 0))


def test_redact_oculta_la_key():
    out = ac.redact("fallo con sk-ant-api03-SECRET123 y otra", "sk-ant-api03-SECRET123")
    assert "SECRET" not in out


# =====================================================================
# Ampliacion: estados de UI, registro, cable/ip, --check, estados del panel
# =====================================================================
def test_parse_multi_estados_y_puntos():
    raw = {"states": {"main": True, "interface_menu": False, "ip_config": "si"},
           "points": {"search_field": {"x": 10, "y": 20}, "menu_item_0": None}}
    pts, states, warns = ac.parse_multi_response(
        json.dumps(raw), (100, 100), ["search_field", "menu_item_0"],
        ["main", "interface_menu", "ip_config", "cable_palette"])
    assert pts == {"search_field": (10, 20)}
    # solo True booleano cuenta: "si", False y ausente -> False
    assert states == {"main": True, "interface_menu": False,
                      "ip_config": False, "cable_palette": False}
    assert any("menu_item_0" in w for w in warns)


def test_parse_multi_sin_points_ni_states():
    pts, states, warns = ac.parse_multi_response("{}", (100, 100), ["a"], ["main"])
    assert pts == {} and states == {"main": False} and warns


def test_parse_multi_invalido_lanza():
    with pytest.raises(ac.AutoCalibrateError):
        ac.parse_multi_response("nada", (100, 100), ["a"], ["main"])


def test_get_set_path():
    d = {}
    ac.set_path(d, ("cable_icons", "serial"), [1, 2])
    ac.set_path(d, ("cable_icon",), [3, 4])
    assert d == {"cable_icons": {"serial": [1, 2]}, "cable_icon": [3, 4]}
    assert ac.get_path(d, ("cable_icons", "serial")) == [1, 2]
    assert ac.get_path(d, ("cable_icons", "copper")) is None
    assert ac.get_path(d, ("nada", "x")) is None
    assert ac.get_path({"a": 5}, ("a", "b")) is None


def test_derive_menu_geometry_ok():
    off, row = ac.derive_menu_geometry((520, 330), (522, 350), (500, 300))
    assert off == [20, 30] and row == 20


@pytest.mark.parametrize("i0,i1,mouse", [
    ((520, 330), (520, 331), (500, 300)),      # fila demasiado baja
    ((520, 330), (520, 900), (500, 300)),      # fila demasiado alta
    ((520, 330), (700, 350), (500, 300)),      # distinta columna
    ((520, 330), (520, 350), (3000, 300)),     # mouse lejos: no es el clic
    ((520, 330), (520, 310), (500, 300)),      # fila negativa
])
def test_derive_menu_geometry_implausible(i0, i1, mouse):
    with pytest.raises(ValueError):
        ac.derive_menu_geometry(i0, i1, mouse)


def test_element_status():
    assert ac.element_status(False, {"status": "ok"}) == "manual"   # sin valor
    assert ac.element_status(False, None) == "manual"
    assert ac.element_status(True, None) == "unverified"            # valor manual sin verificar
    assert ac.element_status(True, {"status": "ok"}) == "ok"
    assert ac.element_status(True, {"status": "manual"}) == "manual"
    assert ac.element_status(True, {"status": "unverified"}) == "unverified"
    assert ac.element_status(True, {}) == "unverified"


def test_check_status():
    assert ac.check_status(True, "main") == "ok"
    assert ac.check_status(True, "ip_config") == "ok"
    assert ac.check_status(False, "main") == "manual"          # se movio
    assert ac.check_status(False, "ip_config") == "unverified"  # quiza la ventana no esta abierta


def test_registry_cubre_los_tres_json():
    reg = ac.build_registry({"cable_icons": {"fiber": [1, 1], "serial": [2, 2]}})
    assert {e.file for e in reg.values()} == {"coords", "cable", "ip"}
    # claves que cable_link.py / configure_ip.py realmente usan
    for k in ("cable_icon", "list_offset", "list_row_height", "cable_icons.serial",
              "cable_icons.copper", "cable_icons.fiber"):
        assert k in reg
    for k in ("desktop_tab", "ip_configuration_item", "static_radio", "close_button",
              "ipv4_address", "subnet_mask", "default_gateway"):
        assert reg[k].file == "ip"
    assert reg["cable_icons.fiber"].path == ("cable_icons", "fiber")
    assert reg["list_offset"].ask == "menu_item_0" and reg["list_row_height"].ask == "menu_item_1"
    assert all(e.state in ac.STATES and e.group in ac.GROUPS for e in reg.values())
    assert len({e.fname for e in reg.values()}) == len(reg)          # nombres de recorte unicos
    assert all("." not in e.fname[:-4] for e in reg.values())


def test_registry_sin_datos_de_cable():
    reg = ac.build_registry(None)
    assert "cable_icons.serial" in reg and "cable_icons.copper" in reg


def test_select_elements_y_parse_groups():
    reg = ac.build_registry()
    assert {e.group for e in ac.select_elements(reg, ("main",))} == {"main"}
    assert ac.parse_groups("all") == ac.GROUPS and ac.parse_groups("") == ac.GROUPS
    assert ac.parse_groups("main, IP") == ("main", "ip")
    with pytest.raises(ac.AutoCalibrateError):
        ac.parse_groups("main,foo")


def test_missing_states():
    reg = ac.build_registry()
    els = ac.select_elements(reg, ("cable", "ip"))
    detected = {"main": True, "cable_palette": True, "interface_menu": False,
                "ip_window": False, "ip_desktop": False, "ip_config": False}
    miss = ac.missing_states(els, detected)
    assert set(miss) == {"interface_menu", "ip_window", "ip_desktop", "ip_config"}
    assert set(miss["interface_menu"]) == {"list_offset", "list_row_height"}
    assert "cable_icon" not in sum(miss.values(), [])


def test_prompt_multi_incluye_estados_y_nombres_ia():
    els = ac.select_elements(ac.build_registry(), ("cable",))
    p = ac.build_multi_prompt(els, (800, 600))
    for s in ("main", "cable_palette", "interface_menu"):
        assert f'"{s}"' in p
    assert "menu_item_0" in p and "menu_item_1" in p
    assert "list_offset" not in p        # a la IA se le pide el item, no el offset
    assert "800x600" in p and "null" in p


def test_cache_soft_con_valor_o_recorte():
    m = _meta()
    assert ac.cache_decision(m, ENV, ac.REQUIRED, soft=("desktop_tab",), have=("desktop_tab",))[0]
    ok, why = ac.cache_decision(m, ENV, ac.REQUIRED, soft=("desktop_tab",), have=())
    assert not ok and "desktop_tab" in why
    m["elements"]["desktop_tab"] = {"status": "unverified", "template": "auto_desktop_tab.png"}
    assert ac.cache_decision(m, ENV, ac.REQUIRED, soft=("desktop_tab",), have=())[0]
