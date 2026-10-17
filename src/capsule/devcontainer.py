"""Reads devcontainer.json and builds the `devcontainer` CLI invocations."""

import json
import logging
from collections.abc import Mapping, Set
from dataclasses import dataclass
from pathlib import Path

from capsule.run_config import RunConfig
from capsule.templates import InvalidJSON

log = logging.getLogger(__name__)

LOCAL_DEVCONTAINER = Path(".devcontainer") / "devcontainer.json"


@dataclass(frozen=True)
class Workspace:
    """A project folder and the devcontainer.json capsule starts it with."""

    folder: Path
    template: str | None = None
    config_path: Path | None = None

    @property
    def devcontainer_json(self) -> Path:
        """The template's devcontainer.json, else the folder's local one."""
        return self.config_path or self.folder / LOCAL_DEVCONTAINER


def load_devcontainer(path: Path) -> dict[str, object]:
    """Reads a devcontainer.json.

    Raises:
        FileNotFoundError: The file does not exist.
        InvalidJSON: The file is not a JSON object.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InvalidJSON(f"Invalid JSON in {path}: {e}") from e

    if not isinstance(data, dict):
        raise InvalidJSON(f"Invalid devcontainer.json {path}: expected a JSON object")

    return data


def mount_paths(devcontainer: Mapping[str, object]) -> set[str]:
    """Returns the source and target paths of the mounts a devcontainer.json declares."""
    mounts = devcontainer.get("mounts", [])
    if not isinstance(mounts, list):
        return set()

    paths: set[str] = set()
    for mount in mounts:
        if isinstance(mount, str):
            for part in mount.split(","):
                key, _, value = part.partition("=")
                if key.strip() in ("source", "target") and value:
                    paths.add(value.strip())
        elif isinstance(mount, dict):
            paths.update(mount[key] for key in ("source", "target") if mount.get(key))

    return paths


def capsule_shell(devcontainer: Mapping[str, object]) -> str | None:
    """Returns `customizations.capsule.shell` from a devcontainer.json, or None."""
    customizations = devcontainer.get("customizations")
    capsule = (
        customizations.get("capsule") if isinstance(customizations, dict) else None
    )
    shell = capsule.get("shell") if isinstance(capsule, dict) else None
    return shell if isinstance(shell, str) else None


def _target_args(workspace: Workspace) -> list[str]:
    args = ["--workspace-folder", str(workspace.folder)]
    if workspace.config_path:
        args += ["--config", str(workspace.config_path)]
        args += ["--id-label", f"capsule.workspace={workspace.folder}"]

    return args


def _remote_env_args(cfg: RunConfig) -> list[str]:
    env = {**cfg.env, "UID": str(cfg.resolved_uid()), "GID": str(cfg.resolved_gid())}
    return [
        arg for key, value in env.items() for arg in ("--remote-env", f"{key}={value}")
    ]


def up_command(
    workspace: Workspace,
    cfg: RunConfig,
    declared_paths: Set[str],
    *,
    rebuild: bool,
    recreate: bool,
) -> list[str]:
    """Builds the `devcontainer up` command for a workspace.

    Args:
        workspace: The workspace to start.
        cfg: The run config whose mounts and env are passed to the container.
        declared_paths: Paths the devcontainer.json already mounts; config
            mounts on either side of them are skipped.
        rebuild: Recreate the container and rebuild its image without cache.
        recreate: Recreate the container.

    Returns:
        The command line.
    """
    cmd = ["devcontainer", "up", *_target_args(workspace)]
    if rebuild or recreate:
        cmd.append("--remove-existing-container")
    if rebuild:
        cmd.append("--build-no-cache")

    for mount in cfg.mounts:
        host, container = RunConfig.expand_mount(mount).split(":")
        if host in declared_paths or container in declared_paths:
            log.debug("Skipping mount %r: already declared in devcontainer.json", mount)
            continue

        cmd += ["--mount", RunConfig.mount_to_devcontainer_format(mount)]

    return cmd + _remote_env_args(cfg)


def exec_command(workspace: Workspace, cfg: RunConfig) -> list[str]:
    """Builds the `devcontainer exec` prefix; append `--` and the command to run."""
    return ["devcontainer", "exec", *_target_args(workspace), *_remote_env_args(cfg)]
