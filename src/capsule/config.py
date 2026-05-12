import logging
import os
from pathlib import Path

_xdg = os.environ.get("XDG_CONFIG_HOME")
CONFIG_DIR = Path(_xdg) / "capsule" if _xdg else Path.home() / ".config" / "capsule"

TEMPLATES_DIR = CONFIG_DIR / "templates"
LOG_FILE = CONFIG_DIR / "capsule.log"
CONFIG_FILE = CONFIG_DIR / "config.toml"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> None:
    fmt = "[%(asctime)s] [%(levelname)s] %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    sh = logging.StreamHandler()
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    root.addHandler(fh)
    root.addHandler(sh)
