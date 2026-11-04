"""
automation._legacy_cli - PUENTE TEMPORAL para el panel antiguo (se elimina en la etapa c).

El panel actual aun lanza consolas (`python -m automation._legacy_cli <herramienta> ...`) y
llama a build.main en proceso. Este modulo traduce esas llamadas a las nuevas funciones de
automation/. No es un flujo soportado: el panel nuevo llamara a las funciones directamente.

Herramientas: calibrate | configure_ip | configure_router
"""

import argparse
import sys

from core import log
from core.errors import CancelledError, PTError


def _run(fn):
    log.set_sink(print)
    try:
        return fn()
    except CancelledError as e:
        print(f"\n  {e}")
        return 1
    except PTError as e:
        print(f"\nERROR: {e}")
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        return 1


def build_main():
    """Equivalente a las llamadas `build.main()` del panel antiguo (lee sys.argv)."""
    from automation import build
    ap = argparse.ArgumentParser(description="Coloca dispositivos en Packet Tracer.")
    ap.add_argument("topology", nargs="?", default=None)
    ap.add_argument("--file")
    ap.add_argument("--catalog", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--pause", type=float, default=0.4)
    ap.add_argument("--filter-delay", type=float, default=0.4)
    ap.add_argument("--countdown", type=int, default=5)
    args = ap.parse_args(sys.argv[1:])
    if args.list_models:
        sys.exit(_run(lambda: build.list_models(args.catalog, print)) or 0)
    text = args.topology
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    if not text:
        ap.error("indica una topologia o --file.")
    code = _run(lambda: build.build_topology(
        text, dry_run=args.dry_run, pause=args.pause, filter_delay=args.filter_delay,
        countdown=args.countdown, catalog_path=args.catalog, log=print))
    if code:
        sys.exit(code)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.exit("uso: python -m automation._legacy_cli <calibrate|configure_ip|configure_router> ...")
    tool, rest = argv[0], argv[1:]
    code = 0
    if tool == "calibrate":
        from automation import calibrate as cal
        ap = argparse.ArgumentParser()
        ap.add_argument("--confidence", type=float, default=0.85)
        ap.add_argument("--grayscale", action="store_true")
        ap.add_argument("--recapture-result", action="store_true")
        ap.add_argument("--manual", default=None)
        ap.add_argument("--list", action="store_true")
        ap.add_argument("--auto", action="store_true")
        ap.add_argument("--check", action="store_true")
        ap.add_argument("--dry-run", action="store_true")
        ap.add_argument("--force", action="store_true")
        ap.add_argument("--only", default="all")
        ap.add_argument("--test-model", default="2911")
        ap.add_argument("--pause", action="store_true")
        a = ap.parse_args(rest)
        if a.auto:
            code = _run(lambda: cal.auto_calibrate(dry_run=a.dry_run, force=a.force, groups=a.only,
                                                   test_model=a.test_model, log=print))
        elif a.check:
            code = _run(lambda: cal.check_calibration(groups=a.only, dry_run=a.dry_run, log=print))
        elif a.list:
            code = _run(lambda: cal.list_reference_images(print))
        elif a.manual:
            code = _run(lambda: cal.calibrate_point(a.manual, log=print))
        else:
            code = _run(lambda: cal.calibrate_by_images(
                confidence=a.confidence, grayscale=a.grayscale,
                recapture_result=a.recapture_result, log=print))
        if a.pause:
            input("\n  ENTER para cerrar...")
    elif tool == "configure_ip":
        from automation import configure_ip as ci
        code = _run(lambda: ci.calibrate_ip_window(log=print))
    elif tool == "configure_router":
        from automation import configure_router as cr
        code = _run(lambda: cr.calibrate_router(log=print))
    else:
        sys.exit(f"herramienta desconocida: {tool}")
    sys.exit(1 if code else 0)


if __name__ == "__main__":
    main()
