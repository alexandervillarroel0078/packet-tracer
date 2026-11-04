"""Controlador de la pestana Calibracion (sin tkinter)."""

import os

from automation import calibrate, cable_link, configure_ip, configure_router
from core import ai_providers
from core import autocalibrate as ac
from core import coords as coords_io
from core import paths, settings
from core.errors import PTError
from core.topology import TopologyFileError, load_topology

# Acciones que pueden mover el mouse (todas con dry_run=True por defecto). Autocalibrar y
# Forzar hacen clic en el buscador y escriben un modelo de prueba (filtered_result);
# "Solo mostrar" y "Verificar" nunca tocan el mouse.
MOUSE_ACTIONS = ("autocalibrate", "force")

GROUP_LABELS = {"main": "Pantalla principal (coords.json)",
                "cable": "Cables (cable_coords.json)",
                "ip": "Ventana IP (ip_config_coords.json)"}

# Texto mostrado segun lo elegido: que dejar abierto en Packet Tracer
GROUP_INSTRUCTIONS = {
    "main": ["Packet Tracer visible, sin ventanas ni menus encima (necesario para todo).",
             "Para filtered_result se usara el buscador: cierra menus y ventanas "
             "(se escribira un modelo de prueba y se limpiara)."],
    "cable": ["Selecciona la categoria de conexiones (rayo): la paleta inferior debe mostrar "
              "los TIPOS de cable.",
              "Para list_offset / list_row_height: con un cable armado, haz clic en un "
              "dispositivo del lienzo y DEJA el mouse quieto encima; la lista de "
              "interfaces debe seguir desplegada."],
    "ip": ["Haz doble clic en un PC para abrir su ventana (pestanas arriba y boton X).",
           "Pasada 1: pestana Desktop (iconos de aplicaciones) para ip_configuration_item.",
           "Pasada 2: Desktop > IP Configuration con Static marcado "
           "(static_radio y los 3 campos). Son excluyentes: una pasada cada vez."],
}


class CalibracionController:
    def __init__(self, shared):
        self.shared = shared

    # ----- texto de ayuda --------------------------------------------------------------
    @staticmethod
    def instructions(groups):
        groups = [g for g in ac.GROUPS if g in groups]
        if not groups:
            return "Elige al menos un grupo."
        lines = ["Antes de pulsar, deja en pantalla:"]
        for g in groups:
            lines.append(f"[{g}] " + GROUP_LABELS[g])
            lines += [f"  - {t}" for t in GROUP_INSTRUCTIONS[g]]
        return "\n".join(lines)

    @staticmethod
    def check_groups(groups):
        groups = [g for g in ac.GROUPS if g in (groups or [])]
        if not groups:
            raise PTError("elige al menos un grupo (main, cable o ip).")
        return groups

    @staticmethod
    def _need_key():
        cfg = settings.read_settings()
        name = ai_providers.label(cfg["provider"])
        if not cfg["has_key"]:
            raise PTError(f"falta la API key de {name} (proveedor activo): configurala en la "
                          "pestana Ajustes.")
        if not cfg["model"]:
            raise PTError(f"falta el modelo de {name}: configuralo en la pestana Ajustes.")

    # ----- IA ----------------------------------------------------------------------------
    def _auto(self, label, groups, *, dry_run, force):
        groups = self.check_groups(groups)
        self._need_key()

        def job(ctx):
            return calibrate.auto_calibrate(dry_run=dry_run, force=force, groups=groups,
                                            log=ctx.log)

        mouse = not dry_run        # el paso de filtered_result hace clic y escribe
        return self.shared.runner.start(label, job, touches_mouse=mouse,
                                        countdown=self.shared.seconds() if mouse else 0)

    def autocalibrate(self, groups, dry_run=True):
        """Autocalibrar con IA. dry_run=False guarda y escribe en el buscador."""
        return self._auto("Autocalibrar" + (" (solo mostrar)" if dry_run else ""),
                          groups, dry_run=dry_run, force=False)

    def show_only(self, groups):
        """Solo mostrar lo detectado (nunca guarda, nunca toca el mouse)."""
        return self._auto("Solo mostrar (dry-run)", groups, dry_run=True, force=False)

    def force(self, groups, dry_run=True):
        """Autocalibrar ignorando la cache."""
        return self._auto("Autocalibrar FORZADO" + (" (solo mostrar)" if dry_run else ""),
                          groups, dry_run=dry_run, force=True)

    def verify(self, groups):
        """Re-verifica los puntos guardados en pantalla. Sin API y sin mouse."""
        groups = self.check_groups(groups)

        def job(ctx):
            return calibrate.check_calibration(groups=groups, dry_run=False, log=ctx.log)

        return self.shared.runner.start("Verificar puntos guardados", job)

    # ----- estado y overlays ---------------------------------------------------------------
    @staticmethod
    def status_rows(groups=None):
        return ac.collect_status(tuple(groups) if groups else ac.GROUPS)

    @staticmethod
    def status_counts(rows):
        return {k: sum(1 for r in rows if r["status"] == k) for k in ("ok", "manual", "unverified")}

    @staticmethod
    def iter_points(obj, prefix=""):
        """(nombre, x, y) de cada punto [x, y] de un dict de coordenadas (recursivo)."""
        out = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("screen_size", "autocalibrate"):
                    continue
                out.extend(CalibracionController.iter_points(v, k if not prefix else f"{prefix}.{k}"))
        elif (isinstance(obj, (list, tuple)) and len(obj) == 2
              and all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in obj)):
            out.append((prefix, int(round(obj[0])), int(round(obj[1]))))
        return out

    def overlay_calibration(self):
        """[(archivo, color, [(nombre, x, y)...])] de los JSON de coordenadas."""
        spec = (("coords.json", paths.COORDS_PATH, "#22e34a"),
                ("ip_config_coords.json", paths.IP_CONFIG_COORDS_PATH, "#3aa0ff"),
                ("router_coords.json", paths.ROUTER_COORDS_PATH, "#ff9a2e"))
        return [(label, color, self.iter_points(coords_io.load_coords(path)))
                for label, path, color in spec]

    @staticmethod
    def overlay_topology():
        """[(etiqueta, x, y, tipo)] del registro de topologia."""
        if not os.path.exists(paths.TOPOLOGY_ACTUAL_PATH):
            raise PTError("no existe data/topology/topologia_actual.json. Coloca una "
                          "topologia primero.")
        topo = load_topology(paths.TOPOLOGY_ACTUAL_PATH)
        out = []
        for d in topo.get("dispositivos", []):
            pos = d.get("posicion") or [0, 0]
            try:
                x, y = int(round(pos[0])), int(round(pos[1]))
            except (TypeError, ValueError, IndexError):
                continue
            modelo = d.get("modelo")
            nombre = d.get("nombre", "?")
            out.append((f"{nombre} ({modelo})" if modelo else nombre, x, y,
                        str(d.get("tipo", "")).lower()))
        if not out:
            raise PTError("el registro no tiene dispositivos.")
        return out

    # ----- captura manual con F8 -------------------------------------------------------------
    @staticmethod
    def manual_points():
        return list(calibrate.MANUAL_KEYS)

    def capture_point(self, name):
        if name not in calibrate.MANUAL_KEYS:
            raise PTError(f"punto no valido: {name}")

        def job(ctx):
            ctx.log("  Pulsa F8 con el mouse sobre el punto (ESC cancela).")
            return calibrate.calibrate_point(name, countdown=0, log=ctx.log, cancel=ctx.cancel)

        return self.shared.runner.start(f"Capturar {name} (F8)", job)

    def capture_ip_window(self):
        def job(ctx):
            return configure_ip.calibrate_ip_window(countdown=0, log=ctx.log, cancel=ctx.cancel)
        return self.shared.runner.start("Calibrar ventana IP (F8)", job)

    def capture_router(self):
        def job(ctx):
            return configure_router.calibrate_router(countdown=0, log=ctx.log, cancel=ctx.cancel)
        return self.shared.runner.start("Calibrar router CLI (F8)", job)

    def list_devices(self):
        try:
            return [d.get("nombre", "?")
                    for d in load_topology(paths.TOPOLOGY_ACTUAL_PATH).get("dispositivos", [])]
        except TopologyFileError:
            return []

    def capture_cable(self, tipo, reference, recalibrate_base=False):
        tipo = (tipo or "").strip()
        if not tipo or not reference:
            raise PTError("indica el tipo de cable (ej. serial) y un dispositivo de referencia "
                          "del registro.")

        def job(ctx):
            return cable_link.calibrate_cable(tipo, reference, recalibrate_base=recalibrate_base,
                                              countdown=0, log=ctx.log, cancel=ctx.cancel)

        return self.shared.runner.start(f"Calibrar cable '{tipo}' (F8)", job)

    def calibrate_images(self, confidence=0.85):
        def job(ctx):
            return calibrate.calibrate_by_images(confidence=confidence, countdown=0,
                                                 log=ctx.log, cancel=ctx.cancel)
        return self.shared.runner.start("Calibrar por imagenes de referencia", job)
