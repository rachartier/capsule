import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from capsule.config import CONFIG_FILE


class _VolumesSection(TypedDict, total=False):
    mounts: list[str]


class _RunSection(TypedDict, total=False):
    shell: str


class _Config(TypedDict, total=False):
    volumes: _VolumesSection
    dotfiles: _VolumesSection
    env: dict[str, str]
    run: _RunSection


@dataclass
class RunConfig:
    mounts: list[str] = field(default_factory=list)
    dotfiles: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    shell: str = "/bin/bash"

    def all_mounts(self) -> list[str]:
        return self.mounts + self.dotfiles


def load_run_config() -> RunConfig:
    if not CONFIG_FILE.exists():
        return RunConfig()

    with open(CONFIG_FILE, "rb") as f:
        data: _Config = tomllib.load(f)  # type: ignore[assignment]

    volumes = data.get("volumes", {})
    dotfiles = data.get("dotfiles", {})
    env_section = data.get("env", {})
    run_section = data.get("run", {})

    return RunConfig(
        mounts=list(volumes.get("mounts", [])),
        dotfiles=list(dotfiles.get("mounts", [])),
        env={k: os.path.expandvars(str(v)) for k, v in env_section.items()},
        shell=run_section.get("shell", "/bin/bash"),
    )


def expand_mount(mount: str) -> str:
    parts = mount.split(":")
    parts[0] = str(Path(os.path.expandvars(parts[0])).expanduser())
    return ":".join(parts)


def mount_to_devcontainer_format(mount: str) -> str:
    parts = expand_mount(mount).split(":")
    return f"type=bind,source={parts[0]},target={parts[1]}"
