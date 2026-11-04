"""Controlador de la pestana Configurar (IP, hostname de routers, config_gen). Sin tkinter."""

from dataclasses import dataclass, field

from automation import configure_ip, configure_router
from core import config_gen, paths
from core.errors import CancelledError, PTError
from core.topology import TopologyFileError, load_topology

# Acciones que pueden mover el mouse (todas con dry_run=True por defecto).
MOUSE_ACTIONS = ("apply_ip", "apply_all_ips", "set_hostname")

MODES = {"Estatico": config_gen.MODE_STATIC, "RIP": config_gen.MODE_RIP}


@dataclass
class ConfigResult:
    configs: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def text(self):
        if not self.configs:
            return "(no hay routers en la topologia)"
        body = "\n\n".join(self.configs[r] for r in self.configs)
        if self.warnings:
            body += "\n\n" + "\n".join(f"[!] {w}" for w in self.warnings)
        return body


class ConfigurarController:
    def __init__(self, shared):
        self.shared = shared

    # ----- dispositivos del registro --------------------------------------------
    def _devices(self):
        try:
            return load_topology(paths.TOPOLOGY_ACTUAL_PATH).get("dispositivos", [])
        except TopologyFileError:
            return []

    def list_pcs(self):
        return [d["nombre"] for d in self._devices()
                if d.get("tipo") not in ("router", "switch") and "nombre" in d]

    def list_routers(self):
        return [d["nombre"] for d in self._devices()
                if d.get("tipo") == "router" and "nombre" in d]

    def device_ip_data(self, name):
        """(ip, mascara, gateway) guardados en el registro para ese dispositivo, o ('','','')."""
        for d in self._devices():
            if d.get("nombre") == name:
                return d.get("ip", ""), d.get("mascara", ""), d.get("gateway", "")
        return "", "", ""

    def pcs_with_ip(self):
        return [d for d in self._devices()
                if d.get("ip") and d.get("mascara") and d.get("gateway")
                and d.get("tipo") not in ("router", "switch")]

    # ----- IP -------------------------------------------------------------------------
    def apply_ip(self, name, ip, mask, gateway, skip_open=False, dry_run=True):
        def job(ctx):
            return configure_ip.configure_device_ip(
                name, ip, mask, gateway, skip_open=skip_open, dry_run=dry_run, countdown=0,
                log=ctx.log, cancel=ctx.cancel)

        label = f"IP de {name}" + (" (dry-run)" if dry_run else "")
        return self.shared.runner.start(label, job, touches_mouse=not dry_run,
                                        countdown=0 if dry_run else self.shared.seconds())

    def apply_all_ips(self, skip_open=False, dry_run=True):
        devices = self.pcs_with_ip()
        if not devices:
            raise PTError("el registro no tiene PCs con IP. Coloca una topologia por redes "
                          "con IPs primero.")

        def job(ctx):
            ok = failed = 0
            for i, d in enumerate(devices, 1):
                if ctx.cancel.is_set():
                    raise CancelledError(f"detenido tras {ok} PC(s)")
                try:
                    configure_ip.configure_device_ip(
                        d["nombre"], d["ip"], d["mascara"], d["gateway"], skip_open=skip_open,
                        dry_run=dry_run, countdown=0, log=ctx.log, cancel=ctx.cancel)
                    ok += 1
                except CancelledError:
                    raise
                except PTError as e:
                    failed += 1
                    ctx.log(f"  FALLO {d['nombre']}: {e}")
                    if "calibrados" in str(e):
                        raise          # sin calibrar: no tiene sentido seguir con las demas
                ctx.progress(i, len(devices))
            ctx.log(f"  PCs: {ok} OK / {failed} fallaron de {len(devices)}")

        label = f"IP de {len(devices)} PC(s)" + (" (dry-run)" if dry_run else "")
        return self.shared.runner.start(label, job, touches_mouse=not dry_run,
                                        countdown=0 if dry_run else self.shared.seconds())

    # ----- hostname --------------------------------------------------------------------
    def set_hostname(self, router, hostname, dry_run=True):
        def job(ctx):
            return configure_router.set_router_hostname(
                router, hostname, dry_run=dry_run, countdown=0, log=ctx.log, cancel=ctx.cancel)

        label = f"Hostname de {router}" + (" (dry-run)" if dry_run else "")
        return self.shared.runner.start(label, job, touches_mouse=not dry_run,
                                        countdown=0 if dry_run else self.shared.seconds())

    # ----- config_gen (solo calculo) -----------------------------------------------------
    def generate_config(self, text, mode_label="Estatico"):
        if not (text or "").strip():
            raise PTError("escribe o carga una topologia en la pestana Colocar primero.")
        mode = MODES.get(mode_label)
        if mode is None:
            raise PTError(f"modo desconocido: {mode_label}")
        try:
            configs, warnings = config_gen.generate_all_configs(text, mode)
        except ValueError as e:                    # TopologyError tambien es ValueError
            raise PTError(str(e)) from e
        return ConfigResult(configs, warnings)
