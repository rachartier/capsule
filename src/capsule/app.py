"""The capsule CLI: the root command and its command groups."""

import importlib.metadata
from typing import Annotated

import typer

from capsule.cli import add, config, containers, doctor, run, templates

app = typer.Typer(no_args_is_help=True)
for group in (templates, add, config, containers, doctor, run):
    app.add_typer(group.app)


@app.callback(invoke_without_command=True)
def _app_callback(
    ctx: typer.Context,
    show_version: Annotated[
        bool,
        typer.Option("-v", "--version", is_eager=True, help="Print version and exit."),
    ] = False,
) -> None:
    if show_version:
        try:
            print(importlib.metadata.version("capsule"))
        except importlib.metadata.PackageNotFoundError:
            print("unknown")
        raise typer.Exit

    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
