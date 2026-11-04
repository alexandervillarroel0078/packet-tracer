"""Controlador de la pestana Ajustes (sin tkinter). La API key nunca se escribe en el log."""

from core import autocalibrate as ac
from core import dpi_aware, settings

MOUSE_ACTIONS = ()      # esta pestana nunca mueve el mouse


class AjustesController:
    def __init__(self, shared):
        self.shared = shared

    def load(self):
        """{"api_key", "model", "has_key"} guardados en .env."""
        return settings.read_settings()

    def save(self, api_key, model):
        """Guarda en .env. Devuelve un mensaje SIN la key. Lanza PTError si algo es invalido."""
        path = settings.save_settings(api_key, model)
        return f"Ajustes guardados en {path} (clave {settings.mask_key(api_key.strip())})."

    def test_connection(self, api_key, model):
        """'Probar conexion' en un hilo (red). El resultado va al log sin la key."""
        settings.validate(api_key, model)
        key, mdl = api_key.strip(), model.strip()

        def job(ctx):
            ctx.log("  Probando conexion con la API...")
            ctx.log("  " + ac.test_connection(key, mdl))

        return self.shared.runner.start("Probar conexion", job)

    @staticmethod
    def dpi_report():
        """Informe de dpi_aware.verify() + escala de Windows. -> (ok, [lineas])."""
        ok, msg = dpi_aware.verify()
        lines = [f"DPI awareness: {dpi_aware.STATUS}", msg,
                 f"Escala de Windows: {int(ac.get_dpi_scale() * 100)} %"]
        phys = dpi_aware.physical_size()
        if phys:
            lines.append(f"Resolucion fisica: {phys[0]}x{phys[1]}")
        if not ok:
            lines.append("[!] Reinicia el panel; si persiste, los clics se desviaran.")
        return ok, lines
