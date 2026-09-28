import argparse
import signal
import sys


def main():
    ap = argparse.ArgumentParser(prog="ds5ctl", description="Gestion de manette DualSense (gyro volant)")
    ap.add_argument("--headless", action="store_true", help="sans interface, avec la config enregistrée")
    ap.add_argument("--profile", help="profil à utiliser en mode --headless")
    args = ap.parse_args()

    if not args.headless:
        from .gui import main as gui_main
        return gui_main()

    from . import config
    from .engine import Engine
    cfg = config.load()
    if args.profile:
        if args.profile not in cfg["profiles"]:
            sys.exit(f"Profil inconnu : {args.profile} (disponibles : {', '.join(cfg['profiles'])})")
        cfg["active_profile"] = args.profile
    eng = Engine(cfg)
    signal.signal(signal.SIGTERM, lambda *_: eng.stop())
    eng.start()
    print(f"ds5ctl actif — profil « {cfg['active_profile']} » ({cfg['profiles'][cfg['active_profile']]['range']}°). Ctrl+C pour quitter.")
    try:
        while eng.is_alive():
            eng.join(0.5)
    except KeyboardInterrupt:
        eng.stop()
        eng.join(2)
    if eng.error:
        sys.exit(eng.error)


if __name__ == "__main__":
    sys.exit(main())
