"""Commands that start a devcontainer and run a shell or command in it."""

import dataclasses
import logging
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from capsule import console as con
from capsule.cli import context
from capsule.config import CONFIG_FILE
from capsule.devcontainer import (
    LOCAL_DEVCONTAINER,
    Workspace,
    capsule_shell,
    exec_command,
    load_devcontainer,
    mount_paths,
    up_command,
)
from capsule.run_config import RunConfig

app = typer.Typer()
log = logging.getLogger(__name__)

_REBUILD_HELP = "Like --recreate, and rebuild the image without the build cache"
_RECREATE_HELP = "Destroy and recreate the container from the current devcontainer.json"


def _require_devcontainer_cli() -> None:
    """Exits with an install hint when the devcontainer CLI is not on PATH."""
    if shutil.which("devcontainer") is None:
        con.error(
            "devcontainer CLI not found in PATH.",
            "Install it with: npm install -g @devcontainers/cli",
        )
        raise typer.Exit(1)


def _resolve_workspace(template_name: str | None) -> Workspace:
    """Picks the template to run: the named one, else the local .devcontainer/, else asks."""
    cwd = Path.cwd()
    if template_name is None and (cwd / LOCAL_DEVCONTAINER).exists():
        return Workspace(cwd)

    if template_name is None:
        entries = context.store.list_templates()
        if not entries:
            con.error(
                "No .devcontainer/devcontainer.json found and no template name given.",
                "Run `capsule add` to store a template first.",
            )
            raise typer.Exit(1)

        con.info("Select a template to run:")
        template_name = con.pick([e.name for e in entries])
        if template_name is None:
            con.info("Aborted.")
            raise typer.Exit(0)

    with context.handle_errors():
        _, json_path = context.store.view(template_name)

    return Workspace(cwd, template=template_name, config_path=json_path)


def _load_run_config(workspace: Workspace, *, quiet: bool) -> RunConfig:
    """Loads config.toml, then applies --quiet and the template's UID/GID override."""
    with context.handle_errors():
        cfg = RunConfig.load(CONFIG_FILE)

    if quiet:
        cfg = dataclasses.replace(cfg, quiet=True)

    if workspace.template:
        override = context.store.load_run_override(workspace.template)
        cfg = dataclasses.replace(
            cfg,
            uid=override.uid if override.uid is not None else cfg.uid,
            gid=override.gid if override.gid is not None else cfg.gid,
        )

    return cfg


def _run_up(up_cmd: Sequence[str], label: str, *, quiet: bool) -> None:
    """Runs `devcontainer up`, streaming its output unless quiet; exits on failure."""
    log.info("devcontainer up: %s", " ".join(up_cmd))
    lines: list[str] = []
    proc = subprocess.Popen(
        up_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )

    with con.launching(f"Starting devcontainer '{label}'...", quiet=quiet) as on_line:
        for raw in proc.stdout or ():
            line = raw.rstrip("\n")
            lines.append(line)
            on_line(line)
        proc.wait()

    if proc.returncode != 0:
        if quiet:
            con.subprocess_output("\n".join(lines))
        con.error("devcontainer up failed.")
        raise typer.Exit(proc.returncode)


def _ensure_container_up(
    template_name: str | None,
    *,
    rebuild: bool = False,
    recreate: bool = False,
    dry_run: bool = False,
    quiet: bool = False,
) -> tuple[Workspace, RunConfig, dict[str, object]]:
    """Starts the workspace's devcontainer, or prints the command on a dry run.

    Returns:
        The workspace, the run config applied to it and its devcontainer.json.
    """
    _require_devcontainer_cli()
    workspace = _resolve_workspace(template_name)
    cfg = _load_run_config(workspace, quiet=quiet)
    with context.handle_errors():
        devcontainer = load_devcontainer(workspace.devcontainer_json)

    up_cmd = up_command(
        workspace, cfg, mount_paths(devcontainer), rebuild=rebuild, recreate=recreate
    )
    if dry_run:
        con.info("Would run: " + " ".join(up_cmd))
    else:
        label = workspace.template or str(devcontainer.get("name", ".devcontainer/"))
        _run_up(up_cmd, label, quiet=cfg.quiet)

    return workspace, cfg, devcontainer


@app.command("run")
def cmd_run(
    template_name: Annotated[
        str | None,
        typer.Argument(help="Template to run (optional if .devcontainer/ exists)"),
    ] = None,
    shell: Annotated[
        str | None, typer.Option("--shell", "-s", help="Shell override")
    ] = None,
    rebuild: Annotated[bool, typer.Option("--rebuild", help=_REBUILD_HELP)] = False,
    recreate: Annotated[bool, typer.Option("--recreate", help=_RECREATE_HELP)] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Print the devcontainer commands without executing"
        ),
    ] = False,
) -> None:
    """Run a devcontainer. Uses the named template, else the local .devcontainer/."""
    workspace, cfg, devcontainer = _ensure_container_up(
        template_name, rebuild=rebuild, recreate=recreate, dry_run=dry_run
    )

    resolved_shell = shell or cfg.shell or capsule_shell(devcontainer) or "/bin/sh"
    exec_cmd = [*exec_command(workspace, cfg), "--", resolved_shell]
    if dry_run:
        con.info("Would exec: " + " ".join(exec_cmd))
        return

    log.info("devcontainer exec: %s", " ".join(exec_cmd))
    os.execvp("devcontainer", exec_cmd)


@app.command(
    "exec",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def cmd_exec(
    ctx: typer.Context,
    rebuild: Annotated[bool, typer.Option("--rebuild", help=_REBUILD_HELP)] = False,
    recreate: Annotated[bool, typer.Option("--recreate", help=_RECREATE_HELP)] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress devcontainer startup output")
    ] = False,
) -> None:
    """Run a one-shot command inside the devcontainer.

    Uses local .devcontainer/ if present. Otherwise the first positional
    argument is the template name and the rest is the command.
    """
    args = ctx.args
    template_name: str | None = None
    command = args
    if not (Path.cwd() / LOCAL_DEVCONTAINER).exists():
        if not args:
            con.error(
                "No .devcontainer/devcontainer.json found and no template name given.",
                "Pass a template name as the first argument, or run `capsule init <template>` first.",
            )
            raise typer.Exit(1)

        template_name, *command = args

    if not command:
        con.error("No command given.", "Usage: capsule exec [<template>] <command...>")
        raise typer.Exit(1)

    workspace, cfg, _ = _ensure_container_up(
        template_name, rebuild=rebuild, recreate=recreate, quiet=quiet
    )
    exec_cmd = [*exec_command(workspace, cfg), "--", *command]
    log.info("devcontainer exec: %s", " ".join(exec_cmd))
    os.execvp("devcontainer", exec_cmd)
