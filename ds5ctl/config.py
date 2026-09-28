import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ds5ctl"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_PROFILE = {
    "gyro_enabled": True,
    "range": 270,            # angle total de braquage (butée à butée), en degrés
    "deadzone": 0.02,        # fraction de la course
    "curve": 1.0,            # 1 = linéaire, >1 = plus doux au centre
    "smoothing": 0.3,        # 0 = aucun lissage
    "invert": False,
    "mix_stick": True,       # additionne le stick gauche physique au gyro
}

DEFAULT_CONFIG = {
    "active_profile": "Par défaut",
    "profiles": {
        "Par défaut": dict(DEFAULT_PROFILE),
        "BeamNG": dict(DEFAULT_PROFILE),
    },
    "device": "wheel",       # "wheel" : volant G29 + manette Xbox ; "wheel_only" : G29 seul ; "xbox" : manette Xbox
    "hide_physical": True,   # masque la vraie DualSense aux jeux (EVIOCGRAB)
    "ps_recenters": True,    # le bouton PS recentre le volant au lieu d'être transmis
}


def load():
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return json.loads(json.dumps(DEFAULT_CONFIG))
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, json.loads(json.dumps(v)))
    for p in cfg["profiles"].values():
        for k, v in DEFAULT_PROFILE.items():
            p.setdefault(k, v)
    if cfg["active_profile"] not in cfg["profiles"]:
        cfg["active_profile"] = next(iter(cfg["profiles"]))
    return cfg


def save(cfg):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    tmp.replace(CONFIG_FILE)
