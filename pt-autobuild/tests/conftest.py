"""
conftest - protecciones globales de la suite.

Ningun test puede mover el mouse ni teclear de verdad: todas las funciones de
pyautogui que actuan sobre el sistema lanzan PyAutoGuiBlocked. Tampoco se puede
escribir en data/ real: las rutas se redirigen a un directorio temporal.
"""

import pytest

BLOCKED = ("click", "doubleClick", "rightClick", "middleClick", "tripleClick",
           "moveTo", "moveRel", "move", "dragTo", "dragRel", "drag", "mouseDown",
           "mouseUp", "scroll", "write", "typewrite", "press", "hotkey",
           "keyDown", "keyUp")


class PyAutoGuiBlocked(AssertionError):
    pass


def _blocked(name):
    def fn(*args, **kwargs):
        raise PyAutoGuiBlocked(f"PyAutoGUI bloqueado en tests: pyautogui.{name}{args!r}")
    fn.__name__ = name
    return fn


@pytest.fixture(autouse=True)
def block_pyautogui(monkeypatch):
    import pyautogui
    for name in BLOCKED:
        if hasattr(pyautogui, name):
            monkeypatch.setattr(pyautogui, name, _blocked(name))
    # los modulos que hicieron `from pyautogui import click` no existen en este proyecto,
    # pero si alguno importa pyautogui como atributo (p. ej. build.pyautogui) es el mismo objeto.
    yield


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirige data/ (coords, registros de topologia) a un directorio temporal."""
    import core.paths as paths
    data = tmp_path / "data"
    topo = data / "topology"
    mapping = {
        "DATA_DIR": str(data),
        "COORDS_PATH": str(data / "coords.json"),
        "IP_CONFIG_COORDS_PATH": str(data / "ip_config_coords.json"),
        "ROUTER_COORDS_PATH": str(data / "router_coords.json"),
        "CABLE_COORDS_PATH": str(data / "cable_coords.json"),
        "PANEL_STATE_PATH": str(data / "panel_state.json"),
        "ENV_PATH": str(tmp_path / ".env"),
        "REFERENCE_IMAGES_DIR": str(tmp_path / "reference_images"),
        "TOPOLOGY_DIR": str(topo),
        "TOPOLOGY_HISTORY_DIR": str(topo / "history"),
        "TOPOLOGY_ACTUAL_PATH": str(topo / "topologia_actual.json"),
    }
    import sys
    originals = {k: getattr(paths, k) for k in mapping}
    for k, v in mapping.items():
        monkeypatch.setattr(paths, k, v)
    # modulos que hicieron `from core.paths import COORDS_PATH` tienen su propia copia
    for name, mod in list(sys.modules.items()):
        if mod is None or not name.startswith(("core.", "automation.", "panel.")):
            continue
        for k, v in mapping.items():
            if getattr(mod, k, None) == originals[k]:
                monkeypatch.setattr(mod, k, v)
    yield mapping


@pytest.fixture(autouse=True)
def isolated_ai_env(monkeypatch):
    """Ninguna clave/proveedor del entorno real (ni lo que guarde un test) se filtra entre tests."""
    for var in ("AI_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL",
                "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"):
        monkeypatch.setenv(var, "")      # vacio = sin definir; monkeypatch lo restaura al salir
    yield
