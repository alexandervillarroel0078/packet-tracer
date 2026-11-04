"""
Tests de la API de funciones de automation/ y de la pureza de core/.

Garantias que se comprueban:
  - dry_run=True por defecto en todas las funciones publicas que actuan sobre la pantalla;
  - errores como excepciones (PTError y subclases), nunca SystemExit;
  - cancelar detiene antes de tocar el mouse (conftest bloquea pyautogui: si se tocara, falla);
  - core/ no usa print/input/sys.exit/msvcrt y core.topology no importa pyautogui.
"""

import ast
import glob
import inspect
import json
import os
import subprocess
import sys
import threading

import pytest

from automation import (add_note, build, cable_link, calibrate, configure_ip,
                        configure_router, move_device, rename_label)
from core import coords as coords_io
from core import log as core_log
from core import paths
from core.errors import (CancelledError, NotCalibratedError, PTError, TopologyFileError)
from core.topology import TopologyError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COORDS = {"search_field": [300, 1000], "filtered_result": [200, 950],
          "canvas": {"top_left": [12, 150], "bottom_right": [1800, 800]}}


@pytest.fixture
def lines():
    out = []
    return out


@pytest.fixture
def calibrated(isolated_data_dir):
    os.makedirs(os.path.dirname(paths.COORDS_PATH), exist_ok=True)
    with open(paths.COORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(COORDS, f)
    return paths.COORDS_PATH


@pytest.fixture
def registry(calibrated):
    """topologia_actual.json minimo con un router y un PC."""
    os.makedirs(os.path.dirname(paths.TOPOLOGY_ACTUAL_PATH), exist_ok=True)
    topo = {"dispositivos": [
        {"id": 1, "tipo": "router", "modelo": "4331", "nombre": "R01", "posicion": [400, 200]},
        {"id": 2, "tipo": "end_device", "modelo": "PC", "nombre": "PC1", "posicion": [500, 400]},
    ]}
    with open(paths.TOPOLOGY_ACTUAL_PATH, "w", encoding="utf-8") as f:
        json.dump(topo, f)
    return topo


# --- dry_run=True por defecto ---------------------------------------------
@pytest.mark.parametrize("fn", [
    add_note.add_note, rename_label.rename_device_label, move_device.move_device,
    cable_link.link_devices, configure_ip.configure_device_ip,
    configure_router.set_router_hostname, build.build_topology, calibrate.auto_calibrate,
])
def test_dry_run_true_por_defecto(fn):
    assert inspect.signature(fn).parameters["dry_run"].default is True


@pytest.mark.parametrize("fn", [
    add_note.add_note, rename_label.rename_device_label, move_device.move_device,
    cable_link.link_devices, configure_ip.configure_device_ip,
    configure_router.set_router_hostname, build.build_topology,
])
def test_funciones_aceptan_log_y_cancel(fn):
    params = inspect.signature(fn).parameters
    assert "log" in params and "cancel" in params


# --- build_topology --------------------------------------------------------
def test_build_dry_run_simple(calibrated, lines):
    assert build.build_topology("2 routers, 1 switch, 3 PC", log=lines.append) is None
    assert any("DRY-RUN" in ln for ln in lines)


def test_build_dry_run_agrupado(calibrated, lines):
    text = "SWITCHES: Sw1\nROUTERS: R01\nRED Red1: 192.168.10.0/24 R01\nPC1 .2\n"
    assert build.build_topology(text, log=lines.append) is None
    assert any("DRY-RUN" in ln for ln in lines)


def test_build_topologia_invalida_lanza_topologyerror(calibrated):
    with pytest.raises(TopologyError):
        build.build_topology("hola mundo")
    with pytest.raises(TopologyError):
        build.build_topology("   ")
    with pytest.raises(TopologyError):
        build.build_topology("SWITCHES: Sw1, Sw1\nROUTERS: R01\n")


def test_build_modelo_inexistente(calibrated):
    with pytest.raises(TopologyError) as ei:
        build.build_topology("2 routers modelo 9999")
    assert "9999" in str(ei.value)


def test_build_sin_calibrar_lanza_notcalibrated():
    with pytest.raises(NotCalibratedError):
        build.build_topology("2 routers")


def test_build_cancelado_antes_de_tocar_el_mouse(calibrated):
    ev = threading.Event()
    ev.set()
    with pytest.raises(CancelledError):
        build.build_topology("2 routers", dry_run=False, countdown=3, cancel=ev)


def test_build_no_ejecuta_nunca_sys_exit(calibrated):
    for bad in ("", "x", "SWITCHES: A, A\n"):
        try:
            build.build_topology(bad)
        except SystemExit:  # pragma: no cover
            pytest.fail("build_topology no debe llamar a sys.exit")
        except PTError:
            pass


# --- otras funciones -------------------------------------------------------
def test_add_note_dry_run_y_errores(calibrated, lines):
    assert add_note.add_note("10.0.0.0/24", 300, 300, log=lines.append) == (300, 300)
    nx, ny = add_note.add_note("x", random_pos=True, log=lines.append)
    assert 12 <= nx <= 1800 and 150 <= ny <= 800
    with pytest.raises(PTError):
        add_note.add_note("x", 5000, 5000)             # fuera del canvas
    with pytest.raises(PTError):
        add_note.add_note("x")                         # sin posicion
    with pytest.raises(PTError):
        add_note.add_note("x", 300, 300, random_pos=True)
    with pytest.raises(PTError):
        add_note.add_note("", 300, 300)


def test_add_note_sin_canvas_calibrado():
    with pytest.raises(NotCalibratedError):
        add_note.add_note("x", 300, 300)


def test_rename_dry_run(calibrated, lines):
    assert rename_label.rename_device_label(400, 200, "R01", category="router",
                                            log=lines.append) == (400, 238)
    with pytest.raises(PTError):
        rename_label.rename_device_label(1, 1, "R01", category="nave")


def test_move_device_dry_run_no_modifica_el_registro(calibrated, registry, lines):
    assert move_device.move_device("R01", 600, 300, log=lines.append) == (600, 300)
    with open(paths.TOPOLOGY_ACTUAL_PATH, encoding="utf-8") as f:
        assert json.load(f)["dispositivos"][0]["posicion"] == [400, 200]
    with pytest.raises(PTError):
        move_device.move_device("R01", 9999, 9999)
    with pytest.raises(TopologyFileError):
        move_device.move_device("NoExiste", 600, 300)


def test_configure_ip_dry_run_y_validaciones(registry, lines):
    configure_ip.configure_device_ip("PC1", "192.168.1.2", "255.255.255.0", "192.168.1.1",
                                     log=lines.append)
    assert any("DRY-RUN" in ln for ln in lines)
    with pytest.raises(PTError):
        configure_ip.configure_device_ip("PC1", "999.1.1.1", "255.255.255.0", "192.168.1.1")
    with pytest.raises(TopologyFileError):
        configure_ip.configure_device_ip("PC9", "192.168.1.2", "255.255.255.0", "192.168.1.1")


def test_configure_ip_real_sin_calibrar_falla_antes_del_mouse(registry):
    with pytest.raises(PTError) as ei:
        configure_ip.configure_device_ip("PC1", "192.168.1.2", "255.255.255.0", "192.168.1.1",
                                         dry_run=False, countdown=0)
    assert "calibrados" in str(ei.value)


def test_router_hostname(registry, lines):
    configure_router.set_router_hostname("R01", "R01", log=lines.append)
    with pytest.raises(PTError):
        configure_router.set_router_hostname("R01", "1mal")        # hostname invalido
    with pytest.raises(PTError):
        configure_router.set_router_hostname("PC1", "PC-1")        # no es router
    with pytest.raises(PTError):
        configure_router.set_router_hostname("R01", "R01", dry_run=False, countdown=0)


def test_link_devices_dry_run_y_faltan_puntos(registry, lines):
    cable_link.link_devices("R01", 3, "PC1", 0, log=lines.append)
    assert any("SIN CALIBRAR" in ln for ln in lines)
    with pytest.raises(PTError):
        cable_link.link_devices("R01", 3, "PC1", 0, dry_run=False, countdown=0)


def test_calibracion_funciones_basicas(lines):
    with pytest.raises(PTError):
        calibrate.calibrate_point("nada")
    out = calibrate.list_reference_images(lines.append)
    assert set(out) == set(calibrate.REF_IMAGES)


# --- captura de puntos (F8) ------------------------------------------------
def _keys(sequence):
    """key_down simulado: devuelve las teclas pulsadas en cada sondeo."""
    it = iter(sequence)

    def kd(vk):
        # F8 se consulta primero en el "suelta F8" y luego en el bucle
        nonlocal_state["vk"] = vk
        return vk in next_set(it)
    nonlocal_state = {}
    cache = {"cur": set()}

    def next_set(iterator):
        # una entrada nueva por cada ciclo de F8
        if nonlocal_state["vk"] == coords_io.VK_F8:
            try:
                cache["cur"] = next(iterator)
            except StopIteration:
                cache["cur"] = set()
        return cache["cur"]
    return kd


def test_capture_point_f8(monkeypatch):
    import pyautogui
    monkeypatch.setattr(pyautogui, "position", lambda: (10, 20))
    seq = [set(), set(), {coords_io.VK_F8}]       # suelta, nada, F8
    p = coords_io.capture_point("x", key_down=_keys(seq), poll=0)
    assert p == [10, 20]


def test_capture_point_esc_y_cancel(monkeypatch):
    assert coords_io.capture_point("x", key_down=lambda vk: vk == coords_io.VK_ESCAPE,
                                   poll=0) is None
    ev = threading.Event()
    ev.set()
    assert coords_io.capture_point("x", key_down=lambda vk: False, cancel=ev, poll=0) is None


def test_capture_point_timeout():
    assert coords_io.capture_point("x", key_down=lambda vk: False, timeout=0.05, poll=0.01) is None


# --- core.log ---------------------------------------------------------------
def test_core_log_sink(tmp_path):
    bad = tmp_path / "x.json"
    bad.write_text("{roto")
    got = []
    core_log.set_sink(got.append)
    try:
        assert coords_io.load_coords(str(bad)) == {}
    finally:
        core_log.set_sink(None)
    assert got and "no se pudo leer" in got[0]
    coords_io.load_coords(str(bad))        # sin sink: no falla ni imprime


# --- pureza de core/ ---------------------------------------------------------
def _core_files():
    return [f for f in glob.glob(os.path.join(ROOT, "core", "*.py"))]


def test_core_sin_print_input_sysexit_msvcrt():
    offenders = []
    for path in _core_files():
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id in ("print", "input"):
                    offenders.append(f"{os.path.basename(path)}:{node.lineno} {f.id}()")
                if (isinstance(f, ast.Attribute) and f.attr == "exit"
                        and isinstance(f.value, ast.Name) and f.value.id == "sys"):
                    offenders.append(f"{os.path.basename(path)}:{node.lineno} sys.exit()")
            if isinstance(node, ast.Import) and any(a.name == "msvcrt" for a in node.names):
                offenders.append(f"{os.path.basename(path)}:{node.lineno} import msvcrt")
    assert offenders == []


def test_core_topology_no_importa_pyautogui():
    code = ("import sys; sys.path.insert(0, %r); "
            "import core.topology, core.config_gen, core.validate; "
            "sys.exit(1 if 'pyautogui' in sys.modules else 0)" % ROOT)
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_automation_sin_print_ni_sysexit_salvo_puente_temporal():
    offenders = []
    for path in glob.glob(os.path.join(ROOT, "automation", "*.py")):
        if os.path.basename(path) == "_legacy_cli.py":
            continue
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id in ("print", "input"):
                    offenders.append(f"{os.path.basename(path)}:{node.lineno} {f.id}()")
                if (isinstance(f, ast.Attribute) and f.attr == "exit"
                        and isinstance(f.value, ast.Name) and f.value.id == "sys"):
                    offenders.append(f"{os.path.basename(path)}:{node.lineno} sys.exit()")
    assert offenders == []
