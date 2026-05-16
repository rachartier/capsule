import contextlib
import difflib
import json
import logging
import os
import shutil
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from capsule import console as con
from capsule.config import CONFIG_FILE, TEMPLATES_DIR
from capsule.run_config import RunConfig
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
    NoProvenance,
    TemplateAlreadyExists,
    TemplateNotFound,
    TemplateStore,
)

app = typer.Typer(no_args_is_help=True)
log = logging.getLogger(__name__)
store = TemplateStore(TEMPLATES_DIR)


@contextlib.contextmanager
def _handle_errors():
    try:
        yield
    except TemplateNotFound as e:
        hint = "Run `capsule list` to see available templates."
        msg = str(e)
        start = msg.find("'")
        end = msg.find("'", start + 1)
        if start != -1 and end != -1:
            queried = msg[start + 1 : end]
            names = [t["name"] for t in store.list_templates()]
            matches = difflib.get_close_matches(queried, names, n=1, cutoff=0.6)
            if matches:
                hint = f"Did you mean '{matches[0]}'? {hint}"
        con.error(msg, hint)
        raise typer.Exit(1) from e
    except TemplateAlreadyExists as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except FileExistsError as e:
        con.error(str(e), "Use --force to overwrite.")
        raise typer.Exit(1) from e
    except NoProvenance as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except (
        MissingDevcontainer,
        InvalidJSON,
        FileNotFoundError,
        RemoteFetchError,
        GitSubpathNotFound,
    ) as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e


@app.command("list")
def cmd_list() -> None:
    """List all available templates."""
    entries = store.list_templates()
    if not entries:
        con.info("No templates found. Use 'capsule add' to create one.")
        return
    rows = [
        [
            e["name"],
            e.get("description", ""),
            datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d %H:%M"),
        ]
        for e in entries
    ]
    con.print_table(["Name", "Description", "Last Modified"], rows)


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

    fetch_ctx = (
        con.spinner("Fetching template...")
        if isinstance(parsed, GitSource)
        else contextlib.nullcontext()
    )
    with _handle_errors(), fetch_ctx, materialize(parsed) as local_path:
        if (local_path / "devcontainer.json").exists():
            template_name = name or _default_template_name(parsed)
            dest = store.add(local_path, template_name)
            if isinstance(parsed, GitSource):
                store.save_provenance(
                    template_name, parsed.url, parsed.ref, parsed.subpath
                )
            con.success(f"Template '{template_name}' added at {dest}")
        else:
            if name is not None:
                con.error("--name cannot be used when adding a directory of templates.")
                raise typer.Exit(1)
            if _add_all_templates(
                local_path,
                store,
                git_source=parsed if isinstance(parsed, GitSource) else None,
            ):
                raise typer.Exit(1)


def _default_template_name(source: LocalSource | GitSource) -> str:
    if isinstance(source, LocalSource):
        return source.path.name
    if source.subpath:
        return Path(source.subpath).name
    last = source.url.rstrip("/").rsplit("/", 1)[-1]
    return last[:-4] if last.endswith(".git") else last


def _add_all_templates(
    directory: Path,
    template_store: TemplateStore,
    git_source: GitSource | None = None,
) -> bool:
    candidates = sorted(
        d
        for d in directory.iterdir()
        if d.is_dir() and (d / "devcontainer.json").exists()
    )
    if not candidates:
        con.error(f"No template directories found in {directory}.")
        return True

    added: list[str] = []
    skipped: list[str] = []
    errors: list[tuple[str, str]] = []

    for d in candidates:
        try:
            template_store.add(d, d.name)
            added.append(d.name)
            if git_source is not None:
                base = git_source.subpath or ""
                subpath = f"{base}/{d.name}" if base else d.name
                template_store.save_provenance(
                    d.name, git_source.url, git_source.ref, subpath
                )
        except TemplateAlreadyExists:
            skipped.append(d.name)
        except (
            FileNotFoundError,
            MissingDevcontainer,
            InvalidJSON,
            PermissionError,
        ) as e:
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
    if not force and not con.confirm(f"Delete template '{template_name}'?"):
        con.info("Aborted.")
        return
    with _handle_errors():
        store.delete(template_name)
        con.success(f"Template '{template_name}' deleted.")


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
    with _handle_errors():
        store.update(template_name, source)
        con.success(f"Template '{template_name}' updated.")


@app.command("rename")
def cmd_rename(
    old_name: Annotated[str, typer.Argument(help="Current template name")],
    new_name: Annotated[str, typer.Argument(help="New template name")],
) -> None:
    """Rename a stored template."""
    with _handle_errors():
        store.rename(old_name, new_name)
        con.success(f"Renamed '{old_name}' to '{new_name}'.")


@app.command("pull")
def cmd_pull(
    template_name: Annotated[
        str, typer.Argument(help="Name of the template to re-fetch")
    ],
) -> None:
    """Re-fetch a template from its recorded git source."""
    with _handle_errors():
        data = store.load_provenance(template_name)
        source = GitSource(
            url=data["url"], ref=data.get("ref"), subpath=data.get("subpath")
        )
        with con.spinner("Fetching template..."), materialize(source) as local_path:
            store.update(template_name, local_path)
        store.save_provenance(template_name, source.url, source.ref, source.subpath)
        con.success(f"Template '{template_name}' updated from {source.url}")


@app.command("view")
def cmd_view(
    template_name: Annotated[str, typer.Argument(help="Name of the template to view")],
) -> None:
    """Pretty-print a template's devcontainer.json."""
    with _handle_errors():
        raw, path = store.view(template_name)
        meta = store.load_meta(template_name)
    if meta:
        parts = [template_name]
        if meta.get("description"):
            parts.append(meta["description"])
        if meta.get("author"):
            parts.append(f"by {meta['author']}")
        title = " — ".join(parts)
    else:
        title = str(path)
    con.print_json(raw, title)


@app.command("search")
def cmd_search(
    keyword: Annotated[
        str, typer.Argument(help="Keyword to search for (case-insensitive)")
    ],
) -> None:
    """Search all templates' devcontainer.json for a keyword."""
    results = store.search(keyword)
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
    with _handle_errors():
        result = store.export(template_name, output_dir)
        con.success(f"Exported '{template_name}' to {result}")


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
    with _handle_errors():
        result = store.init(template_name, dest, force=force)
        con.success(f"Initialized '{template_name}' at {result}")


@app.command("edit")
def cmd_edit(
    template_name: Annotated[str, typer.Argument(help="Template to edit")],
) -> None:
    """Open a template's devcontainer.json in $EDITOR."""
    with _handle_errors():
        _, json_path = store.view(template_name)
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
    os.execvp(editor, [editor, str(json_path)])


@app.command("meta")
def cmd_meta(
    template_name: Annotated[
        str, typer.Argument(help="Template to view or update metadata for")
    ],
    description: Annotated[
        str | None,
        typer.Option("--description", "-d", help="Set a description for the template"),
    ] = None,
    author: Annotated[
        str | None,
        typer.Option("--author", "-a", help="Set the template author"),
    ] = None,
) -> None:
    """View or set metadata (description, author) for a stored template."""
    with _handle_errors():
        if description is None and author is None:
            meta = store.load_meta(template_name)
            if not meta:
                con.info(f"No metadata set for '{template_name}'.")
            else:
                con.print_table(["Key", "Value"], [[k, v] for k, v in sorted(meta.items())])
        else:
            store.save_meta(template_name, description, author)
            con.success(f"Metadata updated for '{template_name}'.")


# Config is a sub-app so `capsule config` shows the config and
# `capsule config init` generates the default file.
config_app = typer.Typer(
    name="config",
    help="Show or initialize the capsule configuration.",
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(config_app)


@config_app.callback()
def cmd_config(ctx: typer.Context) -> None:
    """Show the resolved configuration that will be applied on capsule run."""
    if ctx.invoked_subcommand is not None:
        return
    if not CONFIG_FILE.exists():
        con.info(f"No config file found at {CONFIG_FILE}. Using defaults.")
        return
    cfg = RunConfig.load(CONFIG_FILE)
    rows: list[list[str]] = [["config file", str(CONFIG_FILE)], ["shell", cfg.shell]]
    for mount in cfg.dotfiles:
        rows.append(["dotfile", RunConfig.expand_mount(mount)])
    for mount in cfg.mounts:
        rows.append(["volume", RunConfig.expand_mount(mount)])
    for k, v in cfg.env.items():
        rows.append(["env", f"{k}={v}"])
    con.print_table(["Key", "Value"], rows)


@config_app.command("init")
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
    CONFIG_FILE.write_text(
        """\
# capsule configuration
# https://github.com/rachartier/capsule

[volumes]
# mounts = ["~/my-dir:/home/user/my-dir"]

[dotfiles]
# mounts = ["~/.zshrc:/home/user/.zshrc"]

[env]
# MY_VAR = "value"

[run]
shell = "/bin/bash"
quiet = true
""",
        encoding="utf-8",
    )
    con.success(f"Created config file at {CONFIG_FILE}")


def _find_container_cli() -> str | None:
    for cli in ("docker", "podman"):
        if shutil.which(cli):
            return cli
    return None


def _list_devcontainers(cli: str) -> list[dict]:
    cmd = [
        cli,
        "ps",
        "--all",
        "--format",
        "{{json .}}",
        "--filter",
        "label=devcontainer.local_folder",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    containers = []
    for raw in result.stdout.splitlines():
        stripped = raw.strip()
        if stripped:
            try:
                containers.append(json.loads(stripped))
            except json.JSONDecodeError:
                log.warning("Could not parse container list output: %r", stripped)
    return containers


def _container_workspace(c: dict) -> str:
    for part in c.get("Labels", "").split(","):
        if part.startswith("devcontainer.local_folder="):
            return part.split("=", 1)[1]
    return ""


@app.command("ps")
def cmd_ps() -> None:
    """List all devcontainers (running and stopped)."""
    cli = _find_container_cli()
    if cli is None:
        con.error("docker or podman not found in PATH.")
        raise typer.Exit(1)
    containers = _list_devcontainers(cli)
    if not containers:
        con.info("No devcontainers found.")
        return
    rows = [
        [c.get("Names", "?").lstrip("/"), _container_workspace(c), c.get("Status", "?")]
        for c in containers
    ]
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
    remove: Annotated[
        bool, typer.Option("--rm", help="Remove the container after stopping")
    ] = False,
) -> None:
    """Stop the devcontainer for the current directory (or given workspace path)."""
    cli = _find_container_cli()
    if cli is None:
        con.error("docker or podman not found in PATH.")
        raise typer.Exit(1)
    target = str(Path(workspace).resolve() if workspace else Path.cwd())
    matching = [
        c for c in _list_devcontainers(cli) if _container_workspace(c) == target
    ]
    if not matching:
        con.error(f"No devcontainer found for {target}.")
        raise typer.Exit(1)
    for c in matching:
        cid = c.get("ID") or c.get("Id", "")
        name = c.get("Names", cid).lstrip("/")
        if force:
            subprocess.run([cli, "rm", "-f", cid], check=False)
            con.success(f"Removed container {name}.")
        else:
            status = c.get("Status", "")
            if not status.startswith("Up"):
                con.info(f"Container {name} is already stopped.")
            else:
                subprocess.run([cli, "stop", cid], check=False)
                con.success(f"Stopped container {name}.")
            if remove:
                subprocess.run([cli, "rm", cid], check=False)
                con.success(f"Removed container {name}.")


@app.command("doctor")
def cmd_doctor() -> None:
    """Check that the capsule environment is healthy."""
    all_ok = True

    if shutil.which("devcontainer"):
        con.success("devcontainer CLI found in PATH.")
    else:
        con.error(
            "devcontainer CLI not found.",
            "Install with: npm install -g @devcontainers/cli",
        )
        all_ok = False

    cli = _find_container_cli()
    if cli:
        con.success(f"{cli} found in PATH.")
    else:
        con.error("No container runtime (docker/podman) found in PATH.")
        all_ok = False

    templates = store.list_templates()
    if not templates:
        con.info("No stored templates to validate.")
    else:
        for entry in templates:
            json_path = Path(entry["path"]) / "devcontainer.json"
            if not json_path.exists():
                con.error(f"Template '{entry['name']}': missing devcontainer.json")
                all_ok = False
            else:
                try:
                    json.loads(json_path.read_text(encoding="utf-8"))
                    con.success(f"Template '{entry['name']}': OK")
                except json.JSONDecodeError as e:
                    con.error(f"Template '{entry['name']}': invalid JSON: {e}")
                    all_ok = False

    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("rb") as f:
                tomllib.load(f)
            con.success("config.toml is valid.")
        except Exception as e:
            con.error(f"config.toml is invalid: {e}")
            all_ok = False
    else:
        con.info(f"No config.toml at {CONFIG_FILE} (using defaults).")

    if not all_ok:
        raise typer.Exit(1)


def _ensure_container_up(
    template_name: str | None,
    rebuild: bool = False,
    dry_run: bool = False,
) -> tuple[str | None, RunConfig, str]:
    if shutil.which("devcontainer") is None:
        con.error(
            "devcontainer CLI not found in PATH.",
            "Install it with: npm install -g @devcontainers/cli",
        )
        raise typer.Exit(1)

    local = Path.cwd() / ".devcontainer" / "devcontainer.json"
    config_path: str | None = None

    if template_name:
        with _handle_errors():
            _, json_path = store.view(template_name)
            config_path = str(json_path)
        label = template_name
    elif local.exists():
        try:
            label = json.loads(local.read_text()).get("name", ".devcontainer/")
        except Exception:
            label = ".devcontainer/"
    else:
        entries = store.list_templates()
        if not entries:
            con.error(
                "No .devcontainer/devcontainer.json found and no template name given.",
                "Run `capsule add` to store a template first.",
            )
            raise typer.Exit(1)
        con.info("Select a template to run:")
        picked = con.pick([e["name"] for e in entries])
        if picked is None:
            con.info("Aborted.")
            raise typer.Exit(0)
        with _handle_errors():
            _, json_path = store.view(picked)
            config_path = str(json_path)
        label = picked

    cfg = RunConfig.load(CONFIG_FILE)
    cwd_str = str(Path.cwd())

    up_cmd = ["devcontainer", "up", "--workspace-folder", cwd_str]
    if rebuild:
        up_cmd.append("--remove-existing-container")
    if config_path:
        up_cmd.extend(["--config", config_path])
        up_cmd.extend(["--id-label", f"capsule.workspace={cwd_str}"])
    for mount in cfg.all_mounts():
        up_cmd.extend(["--mount", RunConfig.mount_to_devcontainer_format(mount)])
    for k, v in cfg.env.items():
        up_cmd.extend(["--remote-env", f"{k}={v}"])

    if dry_run:
        con.info("Would run: " + " ".join(up_cmd))
        return config_path, cfg, cwd_str

    log.info("devcontainer up: %s", " ".join(up_cmd))
    lines: list[str] = []
    proc = subprocess.Popen(
        up_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    if proc.stdout is None:
        raise RuntimeError("Failed to open subprocess stdout pipe")
    with con.launching(f"Starting devcontainer '{label}'...", quiet=cfg.quiet) as on_line:
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            lines.append(line)
            on_line(line)
        proc.wait()
    if proc.returncode != 0:
        if cfg.quiet:
            con.subprocess_output("\n".join(lines))
        con.error("devcontainer up failed.")
        raise typer.Exit(proc.returncode)

    return config_path, cfg, cwd_str


def _build_exec_cmd(config_path: str | None, cfg: RunConfig, cwd: str) -> list[str]:
    exec_cmd = ["devcontainer", "exec", "--workspace-folder", cwd]
    if config_path:
        exec_cmd.extend(["--config", config_path])
        exec_cmd.extend(["--id-label", f"capsule.workspace={cwd}"])
    for k, v in cfg.env.items():
        exec_cmd.extend(["--remote-env", f"{k}={v}"])
    return exec_cmd


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
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Print the devcontainer commands without executing"),
    ] = False,
) -> None:
    """Run a devcontainer. Uses local .devcontainer/ if present, otherwise uses the named template."""
    config_path, cfg, cwd = _ensure_container_up(
        template_name, rebuild=rebuild, dry_run=dry_run
    )
    exec_cmd = _build_exec_cmd(config_path, cfg, cwd)
    exec_cmd.extend(["--", shell or cfg.shell])
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
    rebuild: Annotated[
        bool, typer.Option("--rebuild", help="Destroy and recreate the container")
    ] = False,
) -> None:
    """Run a one-shot command inside the devcontainer.

    Uses local .devcontainer/ if present. Otherwise the first positional
    argument is the template name and the rest is the command.
    """
    args = ctx.args
    local = Path.cwd() / ".devcontainer" / "devcontainer.json"

    if local.exists():
        template_name: str | None = None
        command = args
    else:
        if not args:
            con.error(
                "No .devcontainer/devcontainer.json found and no template name given.",
                "Pass a template name as the first argument, or run `capsule init <template>` first.",
            )
            raise typer.Exit(1)
        template_name = args[0]
        command = args[1:]

    if not command:
        con.error("No command given.", "Usage: capsule exec [<template>] <command...>")
        raise typer.Exit(1)

    config_path, cfg, cwd = _ensure_container_up(template_name, rebuild=rebuild)
    exec_cmd = _build_exec_cmd(config_path, cfg, cwd)
    exec_cmd.extend(["--", *command])
    log.info("devcontainer exec: %s", " ".join(exec_cmd))
    os.execvp("devcontainer", exec_cmd)
