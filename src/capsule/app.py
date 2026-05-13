import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from capsule import console as con
from capsule.config import CONFIG_FILE
from capsule.run_config import (
    expand_mount,
    load_run_config,
    mount_to_devcontainer_format,
)
from capsule.sources import (
    GitSource,
    GitSubpathNotFound,
    LocalSource,
    RemoteFetchError,
    materialize,
    parse_source,
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

app = typer.Typer(no_args_is_help=True)
log = logging.getLogger(__name__)


@app.command("list")
def cmd_list() -> None:
    """List all available templates."""
    entries = list_templates()
    if not entries:
        con.info("No templates found. Use 'capsule add' to create one.")
        return
    rows = [
        [e["name"], e["path"], datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d %H:%M")]
        for e in entries
    ]
    con.print_table(["Name", "Path", "Last Modified"], rows)


@app.command("add")
def cmd_add(
    source: Annotated[
        str,
        typer.Argument(
            help="Local path, gh:owner/repo[@ref][/subpath], or a git remote URL"
        ),
    ],
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Override template name")
    ] = None,
    ref: Annotated[
        str | None,
        typer.Option(
            "--ref", help="Git ref (branch/tag/sha). Overrides any inline ref."
        ),
    ] = None,
    subpath: Annotated[
        str | None,
        typer.Option(
            "--subpath",
            help="Subdirectory inside the repo that contains the template. Overrides any inline subpath.",
        ),
    ] = None,
) -> None:
    """Add a new template from a local folder or a git remote."""
    parsed = parse_source(source)
    if isinstance(parsed, GitSource):
        parsed = GitSource(
            parsed.url,
            ref if ref is not None else parsed.ref,
            subpath if subpath is not None else parsed.subpath,
        )
    elif ref is not None or subpath is not None:
        con.error("--ref and --subpath only apply to git remote sources.")
        raise typer.Exit(1)

    try:
        with materialize(parsed) as local_path:
            if (local_path / "devcontainer.json").exists():
                template_name = name or _default_template_name(parsed)
                dest = add_template(local_path, template_name)
                con.success(f"Template '{template_name}' added at {dest}")
            else:
                if name is not None:
                    con.error("--name cannot be used when adding a directory of templates.")
                    raise typer.Exit(1)
                if _add_all_templates(local_path):
                    raise typer.Exit(1)
    except TemplateAlreadyExists as e:
        con.error(str(e), "Run `capsule list` to see existing templates.")
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e
    except (
        FileNotFoundError,
        MissingDevcontainer,
        InvalidJSON,
        RemoteFetchError,
        GitSubpathNotFound,
    ) as e:
        con.error(str(e))
        raise typer.Exit(1) from e


def _default_template_name(source: LocalSource | GitSource) -> str:
    if isinstance(source, LocalSource):
        return source.path.name
    if source.subpath:
        return Path(source.subpath).name
    last = source.url.rstrip("/").rsplit("/", 1)[-1]
    return last[:-4] if last.endswith(".git") else last


def _add_all_templates(directory: Path) -> bool:
    """Add every subdirectory of *directory* that contains a devcontainer.json.

    Returns True if any hard errors occurred (invalid JSON, permission denied).
    TemplateAlreadyExists is treated as a soft skip, not an error.
    """
    candidates = sorted(d for d in directory.iterdir() if d.is_dir() and (d / "devcontainer.json").exists())
    if not candidates:
        con.error(f"No template directories found in {directory}.")
        return True

    added: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    for d in candidates:
        try:
            add_template(d, d.name)
            added.append(d.name)
        except TemplateAlreadyExists:
            skipped.append(d.name)
        except (FileNotFoundError, MissingDevcontainer, InvalidJSON, PermissionError) as e:
            errors.append((d.name, str(e)))

    for n in added:
        con.success(f"Template '{n}' added")
    for n in skipped:
        con.info(f"Template '{n}' already exists, skipped")
    for n, msg in errors:
        con.error(f"{n}: {msg}")

    return bool(errors)


@app.command("delete")
def cmd_delete(
    template_name: Annotated[
        str, typer.Argument(help="Name of the template to delete")
    ],
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Skip confirmation prompt")
    ] = False,
) -> None:
    """Delete a template."""
    if not force:
        if not con.confirm(f"Delete template '{template_name}'?"):
            con.info("Aborted.")
            return
    try:
        delete_template(template_name)
        con.success(f"Template '{template_name}' deleted.")
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("update")
def cmd_update(
    source_path: Annotated[
        str, typer.Argument(help="Path to the source devcontainer folder")
    ],
    name: Annotated[
        str | None, typer.Option("--name", "-n", help="Override template name")
    ] = None,
) -> None:
    """Replace the devcontainer.json in an existing template from a folder."""
    source = Path(source_path).expanduser().resolve()
    template_name = name or source.name
    try:
        update_template(template_name, source)
        con.success(f"Template '{template_name}' updated.")
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e
    except (FileNotFoundError, MissingDevcontainer, InvalidJSON) as e:
        con.error(str(e))
        raise typer.Exit(1) from e


@app.command("view")
def cmd_view(
    template_name: Annotated[str, typer.Argument(help="Name of the template to view")],
) -> None:
    """Pretty-print a template's devcontainer.json."""
    try:
        raw, path = view_template(template_name)
        con.print_json(raw, str(path))
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e


@app.command("search")
def cmd_search(
    keyword: Annotated[
        str, typer.Argument(help="Keyword to search for (case-insensitive)")
    ],
) -> None:
    """Search all templates' devcontainer.json for a keyword."""
    results = search_templates(keyword)
    if not results:
        con.info(f"No matches found for '{keyword}'.")
        return
    rows = [[r["template"], r["field"], r["snippet"]] for r in results]
    con.print_table(["Template Name", "Matching Field", "Value Snippet"], rows)


@app.command("export")
def cmd_export(
    template_name: Annotated[
        str, typer.Argument(help="Name of the template to export")
    ],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Output directory for the zip archive")
    ] = ".",
) -> None:
    """Export a template as a .zip archive."""
    output_dir = Path(output).expanduser().resolve()
    try:
        result = export_template(template_name, output_dir)
        con.success(f"Exported '{template_name}' to {result}")
    except TemplateNotFound as e:
        con.error(str(e), "Run `capsule list` to see available templates.")
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("init")
def cmd_init(
    template_name: Annotated[str, typer.Argument(help="Template to apply")],
    output: Annotated[
        str, typer.Option("--output", "-o", help="Destination directory")
    ] = ".devcontainer",
    force: Annotated[
        bool, typer.Option("--force", "-f", help="Overwrite if destination exists")
    ] = False,
) -> None:
    """Copy a template into the current project as .devcontainer/."""
    dest = Path(output).expanduser().resolve()
    try:
        result = init_template(template_name, dest, force=force)
        con.success(f"Initialized '{template_name}' at {result}")
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

    rows: list[list[str]] = [["config file", str(CONFIG_FILE)], ["shell", cfg.shell]]
    for mount in cfg.dotfiles:
        rows.append(["dotfile", expand_mount(mount)])
    for mount in cfg.mounts:
        rows.append(["volume", expand_mount(mount)])
    for k, v in cfg.env.items():
        rows.append(["env", f"{k}={v}"])
    con.print_table(["Key", "Value"], rows)


@app.command("run")
def cmd_run(
    template_name: Annotated[
        str | None,
        typer.Argument(help="Template to run (optional if .devcontainer/ exists)"),
    ] = None,
    shell: Annotated[
        str | None, typer.Option("--shell", "-s", help="Shell override")
    ] = None,
    rebuild: Annotated[
        bool, typer.Option("--rebuild", help="Destroy and recreate the container")
    ] = False,
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
            con.info(f"Local .devcontainer/ found, ignoring template '{template_name}'.")
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
        up_cmd.extend(["--id-label", f"capsule.workspace={cwd}"])
    for mount in cfg.all_mounts():
        up_cmd.extend(["--mount", mount_to_devcontainer_format(mount)])
    for k, v in cfg.env.items():
        up_cmd.extend(["--remote-env", f"{k}={v}"])

    con.info(f"Starting '{label}' ...")
    log.info("devcontainer up: %s", " ".join(up_cmd))
    result = subprocess.run(up_cmd)
    if result.returncode != 0:
        con.error("devcontainer up failed.")
        raise typer.Exit(result.returncode)

    exec_cmd = ["devcontainer", "exec", "--workspace-folder", cwd]
    if config_path:
        exec_cmd.extend(["--config", config_path])
        exec_cmd.extend(["--id-label", f"capsule.workspace={cwd}"])
    for k, v in cfg.env.items():
        exec_cmd.extend(["--remote-env", f"{k}={v}"])
    exec_cmd.extend(["--", shell or cfg.shell])

    log.info("devcontainer exec: %s", " ".join(exec_cmd))
    os.execvp("devcontainer", exec_cmd)
