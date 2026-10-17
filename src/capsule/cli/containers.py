"""Commands that list and stop devcontainers."""

from pathlib import Path
from typing import Annotated

import typer

from capsule import console as con
from capsule import containers
from capsule.cli import context

app = typer.Typer()


def _require_container_cli() -> str:
    cli = containers.find_container_cli()
    if cli is None:
        con.error("docker or podman not found in PATH.")
        raise typer.Exit(1)

    return cli


@app.command("ps")
def cmd_ps() -> None:
    """List all devcontainers (running and stopped)."""
    cli = _require_container_cli()
    with context.handle_errors():
        found = containers.list_devcontainers(cli)

    if not found:
        con.info("No devcontainers found.")
        return

    rows = [[c.name, c.workspace, c.status] for c in found]
    con.print_table(["Container", "Workspace", "Status"], rows)


@app.command("stop")
def cmd_stop(
    workspace: Annotated[
        str | None,
        typer.Argument(
            help="Workspace path whose container to stop (default: current directory)"
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force", "-f", help="Force-remove the container (stop + delete)"
        ),
    ] = False,
) -> None:
    """Stop the devcontainer for the current directory (or given workspace path)."""
    cli = _require_container_cli()
    target = str(Path(workspace).resolve() if workspace else Path.cwd())
    with context.handle_errors():
        matching = [
            c for c in containers.list_devcontainers(cli) if c.workspace == target
        ]
        if not matching:
            con.error(f"No devcontainer found for {target}.")
            raise typer.Exit(1)

        for c in matching:
            if force:
                containers.remove(cli, c)
                con.success(f"Removed container {c.name}.")
            elif not c.running:
                con.info(f"Container {c.name} is already stopped.")
            else:
                containers.stop(cli, c)
                con.success(f"Stopped container {c.name}.")
