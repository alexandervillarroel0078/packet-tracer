"""
panel.controllers - logica de cada pestana, SIN tkinter.

Cada controlador recibe un Shared (runner de acciones + cuenta regresiva comun + texto de la
topologia) y expone metodos que la vista (panel/<pestana>.py) solo dibuja y conecta a botones.
Asi se prueban con pytest sin abrir ventanas.

Convencion de seguridad: todo metodo que puede mover el mouse tiene `dry_run=True` por
defecto y esta listado en MOUSE_ACTIONS del controlador; la vista debe pasar dry_run=False
de forma explicita (y mostrar el boton en modo "actua de verdad").
"""

from panel.controllers.asistente import AsistenteController
from panel.controllers.calibrar import CalibrarController
from panel.controllers.runner import ActionRunner
from panel.controllers.visible import VisibleController


class Shared:
    """Estado compartido entre pestanas."""

    def __init__(self, runner=None, countdown=5):
        self.runner = runner or ActionRunner()
        self.countdown = countdown          # segundos antes de tomar el mouse
        self.topology_getter = lambda: ""   # la vista de Colocar lo reemplaza
        self.calibrator = CalibrarController(self)    # boton unico "Calibrar"
        self.assistant = AsistenteController(self)    # cable / ip bajo demanda
        self.visual = VisibleController()             # Modo visible, velocidad, pausa

    def topology_text(self):
        return (self.topology_getter() or "").strip()

    def seconds(self):
        try:
            return max(0, int(self.countdown))
        except (TypeError, ValueError):
            return 5
