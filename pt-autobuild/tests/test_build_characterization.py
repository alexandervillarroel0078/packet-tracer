"""
Tests de caracterizacion de build (parseo, layout, IPs, plan de enlaces, dry-run).

Los valores esperados (tests/golden/build.json) se tomaron del codigo ORIGINAL, antes de
dividir build.py, para que la division no cambie el comportamiento. Todo se prueba
llamando a las funciones directamente; nada pasa por linea de comandos ni mueve el mouse
(conftest.py bloquea pyautogui).

Regenerar el golden (solo si el cambio de comportamiento es intencionado):
    python -m tests.test_build_characterization --write
"""

import datetime
import json
import os
import sys
from types import SimpleNamespace

import pytest

from automation import build
from core import topology as topo
from core.paths import CATALOG_PATH, EXAMPLES_DIR

GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "build.json")

FAKE_COORDS = {
    "search_field": [300, 1000],
    "filtered_result": [200, 950],
    "canvas": {"top_left": [12, 150], "bottom_right": [1800, 800]},
}

SIMPLE_TEXTS = [
    "2 routers, 2 switches, 4 PC",
    "3 routers modelo 4331, 1 tablet, 2 laptops",
    "1 router; 1 sw and 3 hosts # comentario",
    "2 foo, 0 routers, 1 server",
    "5 PC",
    "2 end devices",
]

DECLARED = """\
SWITCHES: Sw1, Sw2
ROUTERS:
4331: R01, R02
RED Red1: 192.168.10.0/24
R01-Sw1
PC1 .2
PC2
RED Red2: 192.168.20.0/24 R02 Gig0/0/0
PC3 .10
PC4
ENLACES:
R01 Se0/1/0 R02 10.0.0.0/30
"""

GROUPED_BAD = [
    "SWITCHES: Sw1, Sw1\nROUTERS: R01\n",
    "ROUTERS: R01\nRED Red1: 192.168.10.999/24 R01\nPC1\n",
    "ROUTERS: R01\nRED Red1: 192.168.10.0/24 R01\nPC1 .2\nPC2 .2\n",
]


def _grouped_texts():
    out = {"declarada": DECLARED}
    for name in ("redes.txt", "redes2.txt"):
        with open(os.path.join(EXAMPLES_DIR, name), encoding="utf-8") as f:
            out[name] = f.read()
    return out


def _catalog():
    return topo.load_catalog(CATALOG_PATH)


def _simple_resolved(text, catalog):
    groups, warnings = topo.parse_topology(text)
    errors, resolved = [], []
    for g in groups:
        m = topo.resolve_model(g["category"], g["model"], catalog, errors)
        if m is not None:
            resolved.append({"category": g["category"], "model": m, "count": g["count"]})
    return groups, warnings, resolved, errors


def _normalize_output(text):
    """Quita lo que depende del equipo (DPI / resolucion) y lo que cambia con la fecha."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    out = [ln for ln in lines
           if "DPI awareness" not in ln and "pyautogui.size()" not in ln
           and "DESFASE" not in ln and not ln.lstrip().startswith("Calibra con")]
    return "\n".join(out)


def _capture(fn, *a, **k):
    lines = []
    fn(*a, log=lines.append, **k)
    return _normalize_output("\n".join(lines))


def collect():
    """Calcula TODO lo que se congela en el golden (sin tocar la pantalla)."""
    catalog = _catalog()
    coords = json.loads(json.dumps(FAKE_COORDS))
    g = {}

    g["simple"] = {}
    for t in SIMPLE_TEXTS:
        groups, warnings, resolved, errors = _simple_resolved(t, catalog)
        entry = {"groups": groups, "warnings": warnings, "resolved": resolved,
                 "errors": errors}
        if resolved:
            placements, lw = topo.compute_layout(resolved, coords)
            entry["placements"] = placements
            entry["layout_warnings"] = lw
            entry["dry_run_output"] = _capture(build.print_plan, resolved, placements, lw, True)
        g["simple"][t] = entry

    g["grouped"] = {}
    for name, text in _grouped_texts().items():
        parsed = topo.parse_grouped(text)
        placements, notes, iface_notes, link_notes, warnings = topo.compute_grouped_layout(
            parsed, coords, catalog)
        cabling, cwarn = topo.compute_cabling_plan(parsed, placements, catalog)
        when = datetime.datetime(2026, 1, 1, 12, 0, 0)
        record = topo.build_grouped_record(text, placements, notes, iface_notes,
                                            link_notes, parsed["redes"], coords, when)
        g["grouped"][name] = {
            "is_grouped": topo.is_grouped_syntax(text),
            "parsed": parsed, "placements": placements, "notes": notes,
            "iface_notes": iface_notes, "link_notes": link_notes, "warnings": warnings,
            "cabling_plan": cabling, "cabling_warnings": cwarn, "record": record,
        }

    g["grouped_errors"] = {}
    for t in GROUPED_BAD:
        try:
            topo.parse_grouped(t)
            g["grouped_errors"][t] = None
        except topo.TopologyError as e:
            g["grouped_errors"][t] = str(e)

    g["menu_index"] = {
        "serial_Se0/1/0": topo.compute_menu_index("4331", "Se0/1/0", set(), catalog, tipo="serial"),
        "serial_Se0/2/0_used_Se0/1/0": topo.compute_menu_index(
            "4331", "Se0/2/0", {"Se0/1/0"}, catalog, tipo="serial"),
        "copper_Gig0/0/1": topo.compute_menu_index("4331", "Gig0/0/1", set(), catalog, tipo="copper"),
        "switch_Fa0/3": topo.compute_menu_index(
            "2960", "FastEthernet0/3", set(), catalog, category="switch"),
    }
    g["spread"] = {"0": topo.spread(0, 0, 100), "1": topo.spread(1, 0, 100),
                   "4": topo.spread(4, 12, 1800)}
    g["iface_pos"] = list(topo.calculate_interface_position((100, 100), (300, 100)))
    return json.loads(json.dumps(g, ensure_ascii=False, sort_keys=True, default=str))


def collect_dry_run_grouped():
    """Salida de run_grouped(dry_run=True) por texto, con coords falsas en data/ aislado."""
    from core import coords as coords_io
    from core.paths import COORDS_PATH
    catalog = _catalog()
    coords_io.save_coords(COORDS_PATH, dict(FAKE_COORDS))  # screen_size = real: sin aviso
    data = json.load(open(COORDS_PATH, encoding="utf-8"))
    data.pop("screen_size", None)
    json.dump(data, open(COORDS_PATH, "w", encoding="utf-8"))
    args = SimpleNamespace(dry_run=True, countdown=0, pause=0.0, filter_delay=0.0)
    return {name: _capture(build.run_grouped, text, catalog, args)
            for name, text in _grouped_texts().items()}


@pytest.fixture(scope="module")
def golden():
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_golden_calculos(golden):
    assert collect() == golden["calculos"]


def test_golden_dry_run_agrupado(golden):
    assert collect_dry_run_grouped() == golden["dry_run_agrupado"]


# --- aserciones legibles (documentan lo que el golden congela) ------------
def test_parseo_simple_basico():
    groups, warnings = topo.parse_topology("2 routers, 2 switches, 4 PC")
    assert [(x["category"], x["count"], x["model"]) for x in groups] == [
        ("router", 2, None), ("switch", 2, None), ("end_device", 4, "PC")]
    assert warnings == []


def test_layout_dos_routers_en_459_y_1353():
    catalog = _catalog()
    _, _, resolved, _ = _simple_resolved("2 routers modelo 4331, 2 switches, 4 PC", catalog)
    placements, _ = topo.compute_layout(resolved, FAKE_COORDS)
    pos = [(p["category"], p["x"], p["y"]) for p in placements]
    assert pos[:4] == [("router", 459, 150), ("router", 1353, 150),
                       ("switch", 459, 267), ("switch", 1353, 267)]
    assert pos[4:] == [("end_device", 459, 384), ("end_device", 459, 439),
                       ("end_device", 1353, 384), ("end_device", 1353, 439)]


def test_distribucion_de_ips_declarada():
    catalog = _catalog()
    parsed = topo.parse_grouped(DECLARED)
    placements, *_ = topo.compute_grouped_layout(parsed, FAKE_COORDS, catalog)
    ips = {p["nombre"]: (p.get("ip"), p.get("mascara"), p.get("gateway"))
           for p in placements if p["category"] == "end_device"}
    assert ips["PC1"] == ("192.168.10.2", "255.255.255.0", "192.168.10.1")
    assert ips["PC2"][0] == "192.168.10.3"          # siguiente libre
    assert ips["PC3"][0] == "192.168.20.10"


def test_plan_de_enlaces_declarada():
    catalog = _catalog()
    parsed = topo.parse_grouped(DECLARED)
    placements, *_ = topo.compute_grouped_layout(parsed, FAKE_COORDS, catalog)
    plan, warns = topo.compute_cabling_plan(parsed, placements, catalog)
    assert warns == []
    assert [(e["r1"], e["if1"], e["idx1"], e["r2"], e["if2"], e["idx2"]) for e in plan] == [
        ("R01", "Se0/1/0", 3, "R02", "Se0/1/0", 3)]


def test_errores_de_topologia_agrupada_son_topologyerror():
    for t in GROUPED_BAD:
        with pytest.raises(topo.TopologyError):
            topo.parse_grouped(t)


def test_dry_run_no_toca_pyautogui(golden):
    # conftest bloquea pyautogui: si run_grouped(dry_run) hiciera un clic, fallaria aqui
    out = collect_dry_run_grouped()
    assert all("DRY-RUN" in v for v in out.values())


if __name__ == "__main__":
    if "--write" not in sys.argv:
        sys.exit("usa --write para regenerar el golden")
    import tempfile
    import core.paths as paths
    tmp = tempfile.mkdtemp()
    paths.COORDS_PATH = os.path.join(tmp, "coords.json")
    for m in list(sys.modules.values()):
        if m is not None and getattr(m, "__name__", "").startswith(("core.", "automation.")):
            if hasattr(m, "COORDS_PATH"):
                m.COORDS_PATH = paths.COORDS_PATH
    os.makedirs(os.path.dirname(GOLDEN_PATH), exist_ok=True)
    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        json.dump({"calculos": collect(), "dry_run_agrupado": collect_dry_run_grouped()},
                  f, ensure_ascii=False, indent=1, sort_keys=True)
    print("golden escrito:", GOLDEN_PATH)
