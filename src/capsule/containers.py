"""Lists and stops devcontainers through docker or podman."""

import json
import logging
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Local .devcontainer/ runs get devcontainer.local_folder; template runs get
# only the capsule.workspace id label.
_WORKSPACE_LABELS = ("devcontainer.local_folder", "capsule.workspace")
# Labels are joined with commas, but a value may hold one: split only before a key.
_LABEL_SEPARATOR = re.compile(r",(?=[\w.-]+=)")


class ContainerCliError(Exception):
    """A docker or podman command that failed."""


@dataclass(frozen=True)
class Container:
    """A devcontainer as reported by the container CLI."""

    id: str
    name: str
    workspace: str
    status: str

    @property
    def running(self) -> bool:
        """Whether the container is up."""
        return self.status.startswith("Up")


def find_container_cli() -> str | None:
    """Returns the first of docker or podman found on PATH, or None."""
    return next((cli for cli in ("docker", "podman") if shutil.which(cli)), None)


def _workspace(labels: str) -> str:
    for part in _LABEL_SEPARATOR.split(labels):
        key, _, value = part.partition("=")
        if key in _WORKSPACE_LABELS:
            return value

    return ""


def parse_containers(output: str) -> list[Container]:
    """Parses `ps --format '{{json .}}'` output; unparsable lines are skipped with a warning."""
    containers: list[Container] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            log.warning("Could not parse container list output: %r", stripped)
            continue

        container_id = raw.get("ID") or raw.get("Id", "")
        containers.append(
            Container(
                id=container_id,
                name=raw.get("Names", container_id).lstrip("/"),
                workspace=_workspace(raw.get("Labels", "")),
                status=raw.get("Status", "?"),
            )
        )

    return containers


def _run(cmd: Sequence[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip().splitlines()
        tail = stderr[-1] if stderr else f"exited with status {result.returncode}"
        raise ContainerCliError(f"`{' '.join(cmd)}` failed: {tail}")

    return result.stdout


def list_devcontainers(cli: str) -> list[Container]:
    """Returns every devcontainer, running or stopped, that capsule or VS Code started.

    Raises:
        ContainerCliError: The container CLI failed.
    """
    by_id: dict[str, Container] = {}
    for label in _WORKSPACE_LABELS:
        output = _run(
            [cli, "ps", "--all", "--format", "{{json .}}", "--filter", f"label={label}"]
        )
        by_id.update((c.id, c) for c in parse_containers(output))

    return list(by_id.values())


def stop(cli: str, container: Container) -> None:
    """Stops a container.

    Raises:
        ContainerCliError: The container CLI failed.
    """
    _run([cli, "stop", container.id])


def remove(cli: str, container: Container) -> None:
    """Stops and deletes a container.

    Raises:
        ContainerCliError: The container CLI failed.
    """
    _run([cli, "rm", "-f", container.id])
