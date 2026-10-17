"""Commands that fetch templates from a local folder or a git remote."""

import contextlib
import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

import typer

from capsule import console as con
from capsule.cli import context
from capsule.sources import GitSource, LocalSource, materialize, parse_source
from capsule.templates import (
    InvalidJSON,
    MissingDevcontainer,
    TemplateAlreadyExists,
    TemplateStore,
)

app = typer.Typer()


def _apply_git_options(
    source: LocalSource | GitSource, ref: str | None, subpath: str | None
) -> LocalSource | GitSource:
    """Overrides a git source's ref and subpath; exits if they are given for a local source."""
    if isinstance(source, GitSource):
        return GitSource(
            source.url,
            ref if ref is not None else source.ref,
            subpath if subpath is not None else source.subpath,
        )

    if ref is not None or subpath is not None:
        con.error("--ref and --subpath only apply to git remote sources.")
        raise typer.Exit(1)

    return source


@app.command("add")
def cmd_add(
    source: Annotated[
        str,
        typer.Argument(
            help="Local path, gh:owner/repo\\[@ref]\\[/subpath], or a git remote URL"
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
    with context.handle_errors():
        parsed = _apply_git_options(parse_source(source), ref, subpath)

    git_source = parsed if isinstance(parsed, GitSource) else None
    fetch_ctx = (
        con.spinner("Fetching template...") if git_source else contextlib.nullcontext()
    )
    with context.handle_errors(), fetch_ctx, materialize(parsed) as local_path:
        if (local_path / "devcontainer.json").exists():
            template_name = name or _default_template_name(parsed)
            dest = context.store.add(local_path, template_name)
            if git_source:
                context.store.save_provenance(template_name, git_source)
            con.success(f"Template '{template_name}' added at {dest}")
            return

        if name is not None:
            con.error("--name cannot be used when adding a directory of templates.")
            raise typer.Exit(1)

        if _add_all_templates(local_path, context.store, git_source=git_source):
            raise typer.Exit(1)


def _default_template_name(source: LocalSource | GitSource) -> str:
    """Returns the source's last path segment: folder, subpath or repo name."""
    if isinstance(source, LocalSource):
        return source.path.name

    if source.subpath:
        return Path(source.subpath).name

    return source.url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def _add_all_templates(
    directory: Path,
    template_store: TemplateStore,
    git_source: GitSource | None = None,
) -> bool:
    """Adds each subdirectory holding a devcontainer.json as a template.

    Existing templates are skipped. Every outcome is printed.

    Returns:
        Whether any template failed or none was found.
    """
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
                subpath = (
                    f"{git_source.subpath}/{d.name}" if git_source.subpath else d.name
                )
                template_store.save_provenance(
                    d.name, dataclasses.replace(git_source, subpath=subpath)
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

    _print_add_results(added, skipped, errors)
    return bool(errors)


def _print_add_results(
    added: Sequence[str], skipped: Sequence[str], errors: Sequence[tuple[str, str]]
) -> None:
    for n in added:
        con.success(f"Template '{n}' added")
    for n in skipped:
        con.info(f"Template '{n}' already exists, skipped")
    for n, msg in errors:
        con.error(f"{n}: {msg}")


@app.command("pull")
def cmd_pull(
    template_name: Annotated[
        str, typer.Argument(help="Name of the template to re-fetch")
    ],
) -> None:
    """Re-fetch a template from its recorded git source."""
    with context.handle_errors():
        source = context.store.load_provenance(template_name)
        with con.spinner("Fetching template..."), materialize(source) as local_path:
            context.store.update(template_name, local_path)
        context.store.save_provenance(template_name, source)
        con.success(f"Template '{template_name}' updated from {source.url}")
