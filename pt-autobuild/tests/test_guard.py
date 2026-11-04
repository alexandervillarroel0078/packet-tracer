"""Autocomprobacion de las protecciones de conftest.py."""
import os

import pytest

from tests.conftest import PyAutoGuiBlocked


def test_pyautogui_bloqueado():
    import pyautogui
    for fn, args in ((pyautogui.click, (1, 1)), (pyautogui.write, ("x",)),
                     (pyautogui.hotkey, ("ctrl", "a")), (pyautogui.moveTo, (1, 1)),
                     (pyautogui.press, ("a",)), (pyautogui.dragTo, (1, 1))):
        with pytest.raises(PyAutoGuiBlocked):
            fn(*args)


def test_data_dir_aislado(isolated_data_dir):
    import core.paths as paths
    assert paths.COORDS_PATH.startswith(os.path.dirname(isolated_data_dir["DATA_DIR"]))
    assert not os.path.exists(paths.COORDS_PATH)
