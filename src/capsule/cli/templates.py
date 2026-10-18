"""Commands that view and manage the stored templates."""

import os
import shlex
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from capsule import console as con
from capsule.cli import context

app = typer.Typer()


@app.command("list")
def cmd_list() -> None:
    """List all available templates."""
    entries = context.store.list_templates()
    if not entries:
        con.info("No templates found. Use 'capsule add' to create one.")
        return

    rows = [
        [
            e.name,
            e.description,
            datetime.fromtimestamp(e.mtime).strftime("%Y-%m-%d %H:%M"),
        ]
        for e in entries
    ]
    con.print_table(["Name", "Description", "Last Modified"], rows)


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

    with context.handle_errors():
        context.store.delete(template_name)
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
    with context.handle_errors():
        context.store.update(template_name, source)
        con.success(f"Template '{template_name}' updated.")


@app.command("rename")
def cmd_rename(
    old_name: Annotated[str, typer.Argument(help="Current template name")],
    new_name: Annotated[str, typer.Argument(help="New template name")],
) -> None:
    """Rename a stored template."""
    with context.handle_errors():
        context.store.rename(old_name, new_name)
        con.success(f"Renamed '{old_name}' to '{new_name}'.")


@app.command("view")
def cmd_view(
    template_name: Annotated[str, typer.Argument(help="Name of the template to view")],
) -> None:
    """Pretty-print a template's devcontainer.json."""
    with context.handle_errors():
        raw, path = context.store.view(template_name)
        meta = context.store.load_meta(template_name)

    if meta:
        con.print_template_header(
            template_name,
            meta.get("description", ""),
            meta.get("author", ""),
        )

    con.print_json(raw, str(path))


@app.command("search")
def cmd_search(
    keyword: Annotated[
        str, typer.Argument(help="Keyword to search for (case-insensitive)")
    ],
) -> None:
    """Search all templates' devcontainer.json for a keyword."""
    matches = context.store.search(keyword)
    if not matches:
        con.info(f"No matches found for '{keyword}'.")
        return

    rows = [[m.template, m.field, m.snippet] for m in matches]
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
    with context.handle_errors():
        archive = context.store.export(template_name, output_dir)
        con.success(f"Exported '{template_name}' to {archive}")


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
    with context.handle_errors():
        context.store.init(template_name, dest, force=force)
        con.success(f"Initialized '{template_name}' at {dest}")


@app.command("edit")
def cmd_edit(
    template_name: Annotated[str, typer.Argument(help="Template to edit")],
) -> None:
    """Open a template's devcontainer.json in $EDITOR."""
    with context.handle_errors():
        _, json_path = context.store.view(template_name)

    editor = shlex.split(os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano")
    os.execvp(editor[0], [*editor, str(json_path)])


def _show_meta(template_name: str) -> None:
    """Prints a template's metadata and UID/GID override as a table."""
    rows = [[k, v] for k, v in sorted(context.store.load_meta(template_name).items())]
    override = context.store.load_run_override(template_name)
    rows += [
        [key, str(value)]
        for key, value in (("uid", override.uid), ("gid", override.gid))
        if value is not None
    ]
    if not rows:
        con.info(f"No metadata set for '{template_name}'.")
        return

    con.print_table(["Key", "Value"], rows)


def _merge_id(requested: int | None, current: int | None) -> int | None:
    """Applies a --uid/--gid value: unset keeps the current id, negative removes it."""
    if requested is None:
        return current

    return requested if requested >= 0 else None


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
    uid: Annotated[
        int | None,
        typer.Option("--uid", help="Override UID for this template (pass -1 to unset)"),
    ] = None,
    gid: Annotated[
        int | None,
        typer.Option("--gid", help="Override GID for this template (pass -1 to unset)"),
    ] = None,
) -> None:
    """View or set metadata (description, author, uid, gid) for a stored template."""
    with context.handle_errors():
        if description is None and author is None and uid is None and gid is None:
            _show_meta(template_name)
            return

        if description is not None or author is not None:
            context.store.save_meta(template_name, description, author)
        if uid is not None or gid is not None:
            current = context.store.load_run_override(template_name)
            context.store.save_run_override(
                template_name, _merge_id(uid, current.uid), _merge_id(gid, current.gid)
            )

        con.success(f"Metadata updated for '{template_name}'.")
