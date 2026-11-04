"""
core.errors - excepciones del proyecto. core/ nunca llama a sys.exit(): lanza estas
y quien llama (panel o CLI de pruebas) decide como mostrarlas.

    PTError               base; str(e) es un mensaje claro para el usuario
    NotCalibratedError    falta calibrar algo (o el archivo de coordenadas)
    TopologyFileError     registro de topologia ausente / ilegible / dispositivo desconocido
    CancelledError        el usuario cancelo la accion
"""


class PTError(Exception):
    """Error esperable con mensaje para el usuario."""


class NotCalibratedError(PTError):
    pass


class TopologyFileError(PTError):
    pass


class CancelledError(PTError):
    pass


class AutoCalibrateError(PTError):
    """Fallo de la autocalibracion con IA (configuracion, red, API, respuesta invalida)."""
