"""The command that checks capsule's environment."""

import shutil
import tomllib

import typer

from capsule import console as con
from capsule import containers
from capsule.cli import context
from capsule.config import CONFIG_FILE
from capsule.run_config import InvalidConfig, RunConfig
from capsule.templates import InvalidJSON, validate_json

app = typer.Typer()


def _doctor_tools() -> bool:
    """Reports whether the devcontainer CLI and docker or podman are installed."""
    ok = True

    if shutil.which("devcontainer"):
        con.success("devcontainer CLI found in PATH.")
    else:
        con.error(
            "devcontainer CLI not found.",
            "Install with: npm install -g @devcontainers/cli",
        )
        ok = False

    if cli := containers.find_container_cli():
        con.success(f"{cli} found in PATH.")
    else:
        con.error("No container runtime (docker/podman) found in PATH.")
        ok = False

    return ok


def _doctor_templates() -> bool:
    """Reports whether every stored template has a valid devcontainer.json."""
    templates = context.store.list_templates()
    if not templates:
        con.info("No stored templates to validate.")
        return True

    ok = True

    for entry in templates:
        json_path = entry.path / "devcontainer.json"
        if not json_path.exists():
            con.error(f"Template '{entry.name}': missing devcontainer.json")
            ok = False
            continue

        try:
            validate_json(json_path)
            con.success(f"Template '{entry.name}': OK")
        except InvalidJSON as e:
            con.error(f"Template '{entry.name}': {e}")
            ok = False

    return ok


def _doctor_config() -> bool:
    """Reports whether config.toml, if any, is valid."""
    if not CONFIG_FILE.exists():
        con.info(f"No config.toml at {CONFIG_FILE} (using defaults).")
        return True

    try:
        RunConfig.load(CONFIG_FILE)
    except (InvalidConfig, tomllib.TOMLDecodeError) as e:
        con.error(f"config.toml is invalid: {e}")
        return False

    con.success("config.toml is valid.")
    return True


@app.command("doctor")
def cmd_doctor() -> None:
    """Check that the capsule environment is healthy."""
    results = [_doctor_tools(), _doctor_templates(), _doctor_config()]
    if not all(results):
        raise typer.Exit(1)
