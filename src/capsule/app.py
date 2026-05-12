import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.json import JSON
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from capsule import console as con
from capsule.config import CONFIG_FILE
from capsule.run_config import (
    expand_mount,
    load_run_config,
    mount_to_devcontainer_format,
)
from capsule.templates import (
    InvalidJSON,
    MissingDevcontainer,
    TemplateAlreadyExists,
    TemplateNotFound,
    add_template,
    delete_template,
    export_template,
    init_template,
    list_templates,
    search_templates,
    update_template,
    view_template,
)

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")
log = logging.getLogger(__name__)


@app.command("list")
def cmd_list() -> None:
    """List all available templates."""
    entries = list_templates()
    if not entries:
        con.info("No templates found. Use [bold]capsule add[/bold] to create one.")
        return
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Name")
    table.add_column("Path")
    table.add_column("Last Modified")
    for e in entries:
        mtime = datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d %H:%M")
        table.add_row(e["name"], e["path"], mtime)
    con.console.print(table)


@app.command("add")
def cmd_add(
    source_path: Annotated[str, typer.Argument(help="Path to the source devcontainer folder")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Override template name")] = None,
) -> None:
    """Add a new template from a local folder."""
    source = Path(source_path).expanduser().resolve()
    template_name = name or source.name
    try:
        dest = add_template(source, template_name)
        con.success(f"Template [bold]{template_name}[/bold] added at {dest}")
    except FileNotFoundError as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except MissingDevcontainer as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except TemplateAlreadyExists as e:
        con.error(str(e), "Run `capsule list` to see existing templates.")
        raise typer.Exit(1) from e
    except InvalidJSON as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("delete")
def cmd_delete(
    template_name: Annotated[str, typer.Argument(help="Name of the template to delete")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation prompt")] = False,
) -> None:
    """Delete a template."""
    if not force:
        confirmed = Confirm.ask(f"Delete template [bold]{template_name}[/bold]?")
        if not confirmed:
            con.info("Aborted.")
            return
    try:
        delete_template(template_name)
        con.success(f"Template [bold]{template_name}[/bold] deleted.")
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("update")
def cmd_update(
    template_name: Annotated[str, typer.Argument(help="Name of the template to update")],
    new_devcontainer_path: Annotated[str, typer.Argument(help="Path to the new devcontainer.json")],
) -> None:
    """Replace the devcontainer.json in an existing template."""
    new_path = Path(new_devcontainer_path).expanduser().resolve()
    try:
        update_template(template_name, new_path)
        con.success(f"Template [bold]{template_name}[/bold] updated.")
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e
    except FileNotFoundError as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except InvalidJSON as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("view")
def cmd_view(
    template_name: Annotated[str, typer.Argument(help="Name of the template to view")],
) -> None:
    """Pretty-print a template's devcontainer.json."""
    try:
        raw, path = view_template(template_name)
        con.console.print(Panel(JSON(raw), title=str(path), border_style="blue", title_align="left"))
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e


@app.command("search")
def cmd_search(
    keyword: Annotated[str, typer.Argument(help="Keyword to search for (case-insensitive)")],
) -> None:
    """Search all templates' devcontainer.json for a keyword."""
    results = search_templates(keyword)
    if not results:
        con.info(f"No matches found for [bold]{keyword}[/bold].")
        return
    table = Table(show_header=True, header_style="bold blue")
    table.add_column("Template Name")
    table.add_column("Matching Field")
    table.add_column("Value Snippet")
    for r in results:
        table.add_row(r["template"], r["field"], r["snippet"])
    con.console.print(table)


@app.command("export")
def cmd_export(
    template_name: Annotated[str, typer.Argument(help="Name of the template to export")],
    output: Annotated[str, typer.Option("--output", "-o", help="Output directory for the zip archive")] = ".",
) -> None:
    """Export a template as a .zip archive."""
    output_dir = Path(output).expanduser().resolve()
    try:
        result = export_template(template_name, output_dir)
        con.success(f"Exported [bold]{template_name}[/bold] to {result}")
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("init")
def cmd_init(
    template_name: Annotated[str, typer.Argument(help="Template to apply")],
    output: Annotated[str, typer.Option("--output", "-o", help="Destination directory")] = ".devcontainer",
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite if destination exists")] = False,
) -> None:
    """Copy a template into the current project as .devcontainer/."""
    dest = Path(output).expanduser().resolve()
    try:
        result = init_template(template_name, dest, force=force)
        con.success(f"Initialized [bold]{template_name}[/bold] at {result}")
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e
    except FileExistsError as e:
        con.error(str(e), "Use --force to overwrite.")
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("config")
def cmd_config() -> None:
    """Show the resolved configuration that will be applied on capsule run."""
    if not CONFIG_FILE.exists():
        con.info(f"No config file found at {CONFIG_FILE}. Using defaults.")
        return

    cfg = load_run_config()

    table = Table(show_header=True, header_style="bold blue", box=None, pad_edge=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("config file", str(CONFIG_FILE))
    table.add_row("shell", cfg.shell)

    for mount in cfg.dotfiles:
        table.add_row("dotfile", expand_mount(mount))
    for mount in cfg.mounts:
        table.add_row("volume", expand_mount(mount))
    for k, v in cfg.env.items():
        table.add_row("env", f"{k}={v}")

    con.console.print(table)


@app.command("run")
def cmd_run(
    template_name: Annotated[str | None, typer.Argument(help="Template to run (optional if .devcontainer/ exists)")] = None,
    shell: Annotated[str | None, typer.Option("--shell", "-s", help="Shell override")] = None,
    rebuild: Annotated[bool, typer.Option("--rebuild", help="Destroy and recreate the container")] = False,
) -> None:
    """Run a devcontainer. Uses local .devcontainer/ if present, otherwise uses the named template."""
    if shutil.which("devcontainer") is None:
        con.error(
            "devcontainer CLI not found in PATH.",
            "Install it with: npm install -g @devcontainers/cli",
        )
        raise typer.Exit(1)

    local = Path.cwd() / ".devcontainer" / "devcontainer.json"
    config_path: str | None = None

    if local.exists():
        label = ".devcontainer/"
        if template_name:
            con.info(f"Local .devcontainer/ found, ignoring template [bold]{template_name}[/bold].")
    elif template_name:
        try:
            _, json_path = view_template(template_name)
            config_path = str(json_path)
        except TemplateNotFound as e:
            con.error(str(e), "Run `capsule list` to see available templates.")
            raise typer.Exit(1) from e
        label = template_name
    else:
        con.error(
            "No .devcontainer/devcontainer.json found and no template name given.",
            "Run `capsule init <template>` first, or pass a template name.",
        )
        raise typer.Exit(1)

    cfg = load_run_config()
    cwd = str(Path.cwd())

    up_cmd = ["devcontainer", "up", "--workspace-folder", cwd]
    if rebuild:
        up_cmd.append("--remove-existing-container")
    if config_path:
        up_cmd.extend(["--config", config_path])
    for mount in cfg.all_mounts():
        up_cmd.extend(["--mount", mount_to_devcontainer_format(mount)])
    for k, v in cfg.env.items():
        up_cmd.extend(["--remote-env", f"{k}={v}"])

    con.info(f"Starting [bold]{label}[/bold] ...")
    log.info("devcontainer up: %s", " ".join(up_cmd))
    result = subprocess.run(up_cmd)
    if result.returncode != 0:
        con.error("devcontainer up failed.")
        raise typer.Exit(result.returncode)

    exec_cmd = ["devcontainer", "exec", "--workspace-folder", cwd]
    if config_path:
        exec_cmd.extend(["--config", config_path])
    exec_cmd.extend(["--", shell or cfg.shell])

    log.info("devcontainer exec: %s", " ".join(exec_cmd))
    os.execvp("devcontainer", exec_cmd)
