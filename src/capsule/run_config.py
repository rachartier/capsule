import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunConfig:
    mounts: list[str] = field(default_factory=list)
    dotfiles: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    shell: str = "/bin/bash"

    def all_mounts(self) -> list[str]:
        return self.mounts + self.dotfiles

    @classmethod
    def load(cls, path: Path) -> "RunConfig":
        if not path.exists():
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(
            mounts=list(data.get("volumes", {}).get("mounts", [])),
            dotfiles=list(data.get("dotfiles", {}).get("mounts", [])),
            env={k: os.path.expandvars(str(v)) for k, v in data.get("env", {}).items()},
            shell=data.get("run", {}).get("shell", "/bin/bash"),
        )

    @staticmethod
    def expand_mount(mount: str) -> str:
        parts = mount.split(":")
        parts[0] = str(Path(os.path.expandvars(parts[0])).expanduser())
        return ":".join(parts)

    @staticmethod
    def mount_to_devcontainer_format(mount: str) -> str:
        parts = RunConfig.expand_mount(mount).split(":")
        return f"type=bind,source={parts[0]},target={parts[1]}"
