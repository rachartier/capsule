"""XDG-aware paths for capsule's config, template store and log file."""

import logging
import os
from pathlib import Path

CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "capsule"
)

TEMPLATES_DIR = CONFIG_DIR / "templates"
LOG_FILE = CONFIG_DIR / "capsule.log"
CONFIG_FILE = CONFIG_DIR / "config.toml"


def setup_logging() -> None:
    """Sends all log records to LOG_FILE and warnings or worse to stderr."""
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.WARNING)
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
