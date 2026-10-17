"""Commands that show or create the capsule config file."""

from typing import Annotated

import typer

from capsule import console as con
from capsule.cli import context
from capsule.config import CONFIG_FILE
from capsule.run_config import RunConfig

# Config is a sub-app so `capsule config` shows the config and
# `capsule config init` generates the default file.
app = typer.Typer(
    name="config",
    help="Show or initialize the capsule configuration.",
    invoke_without_command=True,
    no_args_is_help=False,
)

_DEFAULT_CONFIG = """\
# capsule configuration
# https://github.com/rachartier/capsule

[volumes]
# mounts = ["~/my-dir:/home/user/my-dir"]

[env]
# MY_VAR = "value"

[run]
# shell = "/bin/bash"  # global shell override; per-template: set customizations.capsule.shell in devcontainer.json
quiet = false
# uid = 1000  # passed as UID env var; defaults to host uid
# gid = 1000  # passed as GID env var; defaults to host gid
"""


@app.callback()
def cmd_config(ctx: typer.Context) -> None:
    """Show the resolved configuration that will be applied on capsule run."""
    if ctx.invoked_subcommand is not None:
        return

    if not CONFIG_FILE.exists():
        con.info(f"No config file found at {CONFIG_FILE}. Using defaults.")
        return

    with context.handle_errors():
        cfg = RunConfig.load(CONFIG_FILE)

    rows = [
        ["config file", str(CONFIG_FILE)],
        ["shell", cfg.shell or "(devcontainer default)"],
        ["uid", str(cfg.resolved_uid())],
        ["gid", str(cfg.resolved_gid())],
    ]
    rows += [["volume", RunConfig.expand_mount(mount)] for mount in cfg.mounts]
    rows += [["env", f"{k}={v}"] for k, v in cfg.env.items()]
    con.print_table(["Key", "Value"], rows)


@app.command("init")
def cmd_config_init(
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite if already exists")
    ] = False,
) -> None:
    """Generate a default config.toml in the capsule config directory."""
    if CONFIG_FILE.exists() and not force:
        con.error(
            f"Config file already exists at {CONFIG_FILE}.",
            "Use --force to overwrite.",
        )
        raise typer.Exit(1)

    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(_DEFAULT_CONFIG, encoding="utf-8")
    con.success(f"Created config file at {CONFIG_FILE}")
