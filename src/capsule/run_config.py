import logging
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Matches a still-unexpanded shell variable reference ($VAR or ${VAR}).
_UNEXPANDED_RE = re.compile(r"\$\{?[A-Za-z_]")


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class RunConfig:
    mounts: list[str] = field(default_factory=list)
    dotfiles: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    shell: str | None = None
    quiet: bool = True
    uid: int | None = None
    gid: int | None = None

    def resolved_uid(self) -> int:
        return self.uid if self.uid is not None else os.getuid()

    def resolved_gid(self) -> int:
        return self.gid if self.gid is not None else os.getgid()

    def all_mounts(self) -> list[str]:
        return self.mounts + self.dotfiles

    @classmethod
    def load(cls, path: Path) -> "RunConfig":
        if not path.exists():
            return cls()
        with path.open("rb") as f:
            data = tomllib.load(f)
        env: dict[str, str] = {}
        for k, v in data.get("env", {}).items():
            raw = str(v)
            expanded = os.path.expandvars(raw)
            if _UNEXPANDED_RE.search(expanded):
                log.warning(
                    "Env var '%s': value %r may contain an undefined variable", k, raw
                )
            env[k] = expanded
        return cls(
            mounts=list(data.get("volumes", {}).get("mounts", [])),
            dotfiles=list(data.get("dotfiles", {}).get("mounts", [])),
            env=env,
            shell=data.get("run", {}).get("shell", None),
            quiet=bool(data.get("run", {}).get("quiet", False)),
            uid=_optional_int(data.get("run", {}).get("uid")),
            gid=_optional_int(data.get("run", {}).get("gid")),
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
