"""
app.py - unico punto de entrada de pt-autobuild: abre el panel de control.

    doble clic en iniciar.bat   (o: python app.py)
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    from core import dpi_aware  # noqa: F401  DEBE ir antes de pyautogui
    from panel.panel_control import main as run_panel
    run_panel()


if __name__ == "__main__":
    main()
