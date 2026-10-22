"""Reads and writes the capsule.toml kept beside each template's devcontainer.json."""

import json
import tomllib
from collections.abc import Mapping
from pathlib import Path

STATE_FILE = "capsule.toml"


class InvalidState(Exception):
    """A capsule.toml that cannot be read, so rewriting it would drop its settings."""


def read_state(path: Path) -> dict[str, object]:
    """Reads a capsule.toml; a missing file yields an empty mapping.

    Raises:
        InvalidState: The file exists but is not readable TOML.
    """
    if not path.exists():
        return {}

    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise InvalidState(f"Could not read {path}: {e}") from e


def _toml_table(name: str | None, values: Mapping[str, object]) -> list[str]:
    # json.dumps quotes strings with escapes that TOML basic strings also accept.
    lines = [f"[{name}]"] if name else []
    lines += [f"{key} = {json.dumps(value)}" for key, value in values.items()]
    return lines


def write_state(path: Path, data: Mapping[str, object]) -> None:
    """Writes a capsule.toml, with the `run` and `meta` tables after the top-level keys.

    Top-level keys are written as strings. Empty tables are left out.
    """
    top = {k: str(v) for k, v in data.items() if k not in ("meta", "run")}
    lines = _toml_table(None, top)
    for table in ("run", "meta"):
        values = data.get(table)
        if isinstance(values, dict) and values:
            lines += ["", *_toml_table(table, values)]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
