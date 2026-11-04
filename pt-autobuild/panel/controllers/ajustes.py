"""Controlador de la pestana Ajustes (sin tkinter). Ninguna API key se escribe en el log."""

from core import ai_providers, dpi_aware, settings
from core import autocalibrate as ac

MOUSE_ACTIONS = ()      # esta pestana nunca mueve el mouse


class AjustesController:
    def __init__(self, shared):
        self.shared = shared

    # ----- proveedores ------------------------------------------------------------------
    @staticmethod
    def providers():
        """[(clave, nombre visible)] en el orden del selector."""
        return [(p, ai_providers.label(p)) for p in ai_providers.PROVIDERS]

    @staticmethod
    def key_help(provider):
        """(variable del .env, URL donde sacar la clave) del proveedor."""
        p = ai_providers.normalize_provider(provider)
        return ai_providers.KEY_VARS[p], ai_providers.KEY_URLS[p]

    # ----- ajustes -----------------------------------------------------------------------
    def load(self):
        """{"provider", "providers": {p: {api_key, model, has_key}}, api_key/model/has_key
        del proveedor activo} guardados en .env."""
        return settings.read_settings()

    def save(self, api_key, model, provider=None):
        """Guarda proveedor+clave+modelo en .env. Devuelve un mensaje SIN la key."""
        prov = ai_providers.normalize_provider(provider) if provider else settings.active_provider()
        path = settings.save_settings(api_key, model, prov)
        return (f"Ajustes guardados en {path}: proveedor {ai_providers.label(prov)}, "
                f"modelo {model.strip()} (clave {settings.mask_key(api_key.strip())}).")

    def test_connection(self, api_key, model, provider=None):
        """'Probar conexion' con el proveedor elegido, en un hilo (red). Sin la key en el log."""
        prov = ai_providers.normalize_provider(provider) if provider else settings.active_provider()
        settings.validate(api_key, model, prov)
        key, mdl = api_key.strip(), model.strip()
        name = ai_providers.label(prov)

        def job(ctx):
            ctx.log(f"  Proveedor: {name}   Modelo: {mdl}")
            ctx.log("  Probando conexion con la API...")
            ctx.log("  " + ac.test_connection(key, mdl, provider=prov))

        return self.shared.runner.start(f"Probar conexion ({name})", job)

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
