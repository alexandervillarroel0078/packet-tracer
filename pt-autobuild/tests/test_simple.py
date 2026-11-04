"""Pantalla simple: preflight por accion, flujo de Construir, estado y filtered_result."""

import json
import os

import pytest

from automation import build, calibrate
from core import autocalibrate as ac
from core import paths, preflight
from core.errors import PTError
from panel.controllers import Shared
from panel.controllers.runner import ActionRunner
from panel.controllers.simple import SimpleController
from tests.test_panel_controllers import COORDS, GROUPED, Recorder, calibrated, events, logs  # noqa: F401


@pytest.fixture
def shared():
    return Shared(ActionRunner(sync=True, tick_seconds=0), countdown=0)


@pytest.fixture
def with_key(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(var, "clave-de-prueba-123456")


@pytest.fixture
def no_key(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)


# ----- preflight por accion ---------------------------------------------------------------
def test_construir_solo_exige_main_aunque_haya_ips():
    assert preflight.required_names(GROUPED, "build") == list(preflight.MAIN_NAMES)
    assert preflight.groups_for(preflight.required_names(GROUPED, "build")) == ("main",)


def test_cada_accion_exige_solo_sus_puntos():
    assert preflight.required_names("", "ip") == list(preflight.IP_NAMES)
    assert preflight.required_names("", "cable") == list(preflight.CABLE_NAMES)
    assert not set(preflight.required_names("", "ip")) & set(preflight.MAIN_NAMES)
    with pytest.raises(ValueError):
        preflight.required_names("", "otra")


def test_aviso_de_build_no_lista_puntos_de_ip(calibrated):  # noqa: F811
    res = preflight.run_preflight(GROUPED, action="build", log=lambda m: None)
    assert res.ok
    assert all(n in preflight.MAIN_NAMES for n, _s, _d in res.items)


def test_mensajes_sin_nombres_internos():
    res = preflight.evaluate([], list(preflight.MAIN_NAMES))
    text = res.plain_summary()
    assert "search_field" not in text and "canvas_" not in text and "buscador" in text
    assert "search_field" not in preflight.plain("falta search_field y canvas_top_left")


# ----- estado de una linea ------------------------------------------------------------------
def test_estado_sin_calibrar_y_sin_clave(shared, isolated_data_dir, no_key):
    info = SimpleController(shared).status()
    assert info.calibration_text == "Calibración: falta calibrar (Autocalibrar)"
    assert info.api_text == "API: sin clave" and not info.api_ok


def test_estado_calibrado_y_con_clave(shared, calibrated, with_key):  # noqa: F811
    info = SimpleController(shared).status()
    assert info.calibration_ok and info.calibration_text == "Calibración: OK"
    assert info.api_ok and info.api_text == "API: conectada"


# ----- boton Construir -------------------------------------------------------------------------
def test_construir_calibrado_real_no_autocalibra(shared, calibrated, monkeypatch):  # noqa: F811
    shared.countdown = 3
    cal, bld = Recorder(), Recorder(shared)
    monkeypatch.setattr(calibrate, "auto_calibrate", cal)
    monkeypatch.setattr(build, "build_topology", bld)
    assert SimpleController(shared).build("1 switch, 1 PC", dry_run=False)
    assert cal.calls == [] and bld.calls[0][1]["dry_run"] is False
    assert bld.mouse_flags == [True]
    assert [e[1] for e in events(shared) if e[0] == "tick"] == [3, 2, 1, 0]


def test_construir_sin_calibrar_real_autocalibra_y_construye(shared, isolated_data_dir,
                                                             with_key, monkeypatch):
    bld = Recorder()

    def fake_calibrate(**kw):
        os.makedirs(paths.DATA_DIR, exist_ok=True)
        with open(paths.COORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(COORDS, f)

    cal = Recorder()
    cal_calls = []
    monkeypatch.setattr(calibrate, "auto_calibrate",
                        lambda **kw: (cal_calls.append(kw), fake_calibrate(**kw)))
    monkeypatch.setattr(build, "build_topology", bld)
    SimpleController(shared).build("1 switch, 1 PC", dry_run=False)
    assert cal_calls[0]["dry_run"] is False and cal_calls[0]["groups"] == ["main"]
    assert len(bld.calls) == 1
    text = "\n".join(logs(shared))
    assert "Voy a calibrar" in text and "search_field" not in text


def test_construir_sin_calibrar_dry_run_solo_explica(shared, isolated_data_dir, no_key,
                                                     monkeypatch):
    cal, bld = Recorder(), Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", cal)
    monkeypatch.setattr(build, "build_topology", bld)
    SimpleController(shared).build("1 switch, 1 PC", dry_run=True)    # no exige clave
    assert cal.calls == [] and bld.calls == []
    assert "Voy a calibrar" in "\n".join(logs(shared))


def test_construir_sin_calibrar_real_sin_clave_avisa_en_simple(shared, isolated_data_dir, no_key,
                                                               monkeypatch):
    bld = Recorder()
    monkeypatch.setattr(build, "build_topology", bld)
    with pytest.raises(PTError, match="clave de la IA"):
        SimpleController(shared).build("1 switch, 1 PC", dry_run=False)
    assert bld.calls == [] and not shared.runner.busy


def test_construir_si_la_autocalibracion_no_basta_no_construye(shared, isolated_data_dir,
                                                               with_key, monkeypatch):
    bld = Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", lambda **kw: 1)
    monkeypatch.setattr(build, "build_topology", bld)
    SimpleController(shared).build("1 switch", dry_run=False)
    assert bld.calls == []
    text = "\n".join(logs(shared))
    assert "[ERROR] no pude calibrar" in text and "search_field" not in text


def test_construir_texto_vacio_y_errores_en_lenguaje_simple(shared, calibrated, monkeypatch):  # noqa: F811
    with pytest.raises(PTError):
        SimpleController(shared).build("  ")

    def boom(*a, **k):
        raise PTError("falta calibrar search_field")

    monkeypatch.setattr(build, "build_topology", boom)
    SimpleController(shared).build("1 switch")
    text = "\n".join(logs(shared))
    assert "el buscador de dispositivos" in text and "search_field" not in text


def test_autocalibrar_dry_run_no_llama_a_la_ia(shared, isolated_data_dir, monkeypatch):
    cal = Recorder()
    monkeypatch.setattr(calibrate, "auto_calibrate", cal)
    SimpleController(shared).autocalibrate()
    assert cal.calls == []
    assert "Dry-run" in "\n".join(logs(shared))


# ----- filtered_result ----------------------------------------------------------------------------
def test_descripcion_de_filtered_result_dice_fila_superior_encima_del_buscador():
    desc = ac.DESCRIPTIONS["filtered_result"]
    assert "PRIMER icono de la fila superior" in desc and "ENCIMA del campo de busqueda" in desc
    assert "NO esta a la derecha ni debajo" in desc and ac.FILTERED_RESULT_DESC in desc


SEARCH = (300, 1000)


def test_filtered_result_valido_encima_del_buscador_dentro_del_panel():
    assert ac.filtered_point_error((310, 940), SEARCH) is None
    assert ac.filtered_point_error((300 - ac.FILTERED_MAX_DX, 1000 - ac.FILTERED_MIN_ABOVE),
                                   SEARCH) is None


@pytest.mark.parametrize("point, texto", [
    ((310, 1090), "no esta encima"),                      # debajo (lista de dispositivos)
    ((310, 1003), "no esta encima"),                      # al nivel del campo
    ((600, 1000), "no esta encima"),                      # a su derecha, misma fila
    ((310, 1000 - ac.FILTERED_MAX_ABOVE - 5), "demasiado arriba"),
    ((300 + ac.FILTERED_MAX_DX + 5, 950), "fuera del ancho"),
    ((300 - ac.FILTERED_MAX_DX - 5, 950), "fuera del ancho"),
])
def test_filtered_result_rechazado_por_geometria(point, texto):
    assert texto in ac.filtered_point_error(point, SEARCH)


def test_solo_mostrar_pasa_detected_out_y_expone_puntos_al_overlay(shared, with_key, monkeypatch):
    from panel.controllers.calibracion import CalibracionController
    monkeypatch.setenv("OPENAI_MODEL", "modelo-vision-x")

    def fake(**kw):
        kw["detected_out"].update({"search_field": {"point": [300, 1000], "rejected": False},
                                   "filtered_result": {"point": [310, 1090], "rejected": True}})
        return 0

    monkeypatch.setattr(calibrate, "auto_calibrate", fake)
    c = CalibracionController(shared)
    c.show_only(["main"])
    pts = {n: (x, y, bad) for n, x, y, bad in c.overlay_detected()}
    assert pts["filtered_result"] == (310, 1090, True)
    assert pts["search_field"] == (300, 1000, False)


def test_overlay_detectado_dibuja_cada_punto_con_su_nombre(monkeypatch):
    from panel import overlay
    mgr = overlay.OverlayManager(None, lambda m: None)
    shown = {}
    monkeypatch.setattr(mgr, "_show", lambda kind, markers, legend: shown.update(
        kind=kind, markers=markers, legend=legend))
    monkeypatch.setattr(mgr, "_labels", lambda *a: None)
    mgr.show_detected([("filtered_result", 310, 940, False),
                       ("filtered_result", 310, 1090, True)], None, None)
    names = [m[0] for m in shown["markers"]]
    assert names == ["filtered_result", "filtered_result (RECHAZADO)"]
    assert shown["kind"] == "det" and len(shown["legend"]) == 2
