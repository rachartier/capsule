"""Reads the user's config.toml into the settings applied on capsule run."""

import logging
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Matches a still-unexpanded shell variable reference ($VAR or ${VAR}).
_UNEXPANDED_RE = re.compile(r"\$\{?[A-Za-z_]")


class InvalidConfig(Exception):
    """A config.toml that capsule cannot apply."""


def _validate_mounts(mounts: Sequence[str]) -> list[str]:
    for mount in mounts:
        # devcontainer --mount accepts no options, so ":ro" would be silently dropped.
        if len(mount.split(":")) != 2:
            raise InvalidConfig(
                f"Invalid mount {mount!r}: expected 'host_path:container_path'. "
                "Options such as ':ro' are not supported; declare read-only mounts "
                "in devcontainer.json instead."
            )

    return list(mounts)


def _optional_int(section: Mapping[str, object], key: str) -> int | None:
    value = section.get(key)
    if value is None:
        return None

    error = InvalidConfig(f"Invalid {key} {value!r}: expected an integer.")
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise error

    try:
        return int(value)
    except ValueError as e:
        raise error from e


def _expand_env(raw_env: Mapping[str, object]) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in raw_env.items():
        raw = str(value)
        expanded = os.path.expandvars(raw)
        if _UNEXPANDED_RE.search(expanded):
            log.warning(
                "Env var '%s': value %r may contain an undefined variable", key, raw
            )
        env[key] = expanded

    return env


@dataclass(frozen=True)
class RunConfig:
    """The settings capsule applies to every container it starts."""

    mounts: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    shell: str | None = None
    quiet: bool = True
    uid: int | None = None
    gid: int | None = None

    def resolved_uid(self) -> int:
        """Returns the configured UID, or the host user's UID when unset."""
        return self.uid if self.uid is not None else os.getuid()

    def resolved_gid(self) -> int:
        """Returns the configured GID, or the host user's GID when unset."""
        return self.gid if self.gid is not None else os.getgid()

    @classmethod
    def load(cls, path: Path) -> "RunConfig":
        """Reads a config.toml, expanding variables in env values.

        Args:
            path: The config file. A missing file yields the defaults.

        Returns:
            The parsed config.

        Raises:
            InvalidConfig: The file is not valid TOML or holds an invalid value.
        """
        if not path.exists():
            return cls()

        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise InvalidConfig(f"Invalid TOML in {path}: {e}") from e

        mounts = list(data.get("volumes", {}).get("mounts", []))
        if dotfiles := data.get("dotfiles", {}).get("mounts"):
            log.warning("[dotfiles] is deprecated: move its mounts to [volumes].")
            mounts += dotfiles

        run = data.get("run", {})
        return cls(
            mounts=_validate_mounts(mounts),
            env=_expand_env(data.get("env", {})),
            shell=run.get("shell"),
            quiet=bool(run.get("quiet", False)),
            uid=_optional_int(run, "uid"),
            gid=_optional_int(run, "gid"),
        )

    @staticmethod
    def expand_mount(mount: str) -> str:
        """Expands `~` and `$VAR` in the host side of a `host:container` mount."""
        parts = mount.split(":")
        parts[0] = str(Path(os.path.expandvars(parts[0])).expanduser())
        return ":".join(parts)

    @staticmethod
    def mount_to_devcontainer_format(mount: str) -> str:
        """Converts a `host:container` mount to the devcontainer `--mount` format."""
        parts = RunConfig.expand_mount(mount).split(":")
        return f"type=bind,source={parts[0]},target={parts[1]}"
