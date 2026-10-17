"""The template store and error reporting shared by every command."""

import contextlib
import difflib
from collections.abc import Generator

import typer

from capsule import console as con
from capsule import containers
from capsule.config import TEMPLATES_DIR
from capsule.run_config import InvalidConfig
from capsule.sources import GitSubpathNotFound, RemoteFetchError
from capsule.templates import (
    InvalidJSON,
    MissingDevcontainer,
    NoProvenance,
    TemplateAlreadyExists,
    TemplateNotFound,
    TemplateStore,
)

store = TemplateStore(TEMPLATES_DIR)


@contextlib.contextmanager
def handle_errors() -> Generator[None]:
    """Turns the domain errors raised in the block into a message and exit code 1."""
    try:
        yield
    except TemplateNotFound as e:
        hint = "Run `capsule list` to see available templates."
        names = [t.name for t in store.list_templates()]
        if matches := difflib.get_close_matches(e.name, names, n=1, cutoff=0.6):
            hint = f"Did you mean '{matches[0]}'? {hint}"
        con.error(str(e), hint)
        raise typer.Exit(1) from e
    except FileExistsError as e:
        con.error(str(e), "Use --force to overwrite.")
        raise typer.Exit(1) from e
    except (
        InvalidConfig,
        TemplateAlreadyExists,
        NoProvenance,
        MissingDevcontainer,
        InvalidJSON,
        FileNotFoundError,
        RemoteFetchError,
        GitSubpathNotFound,
        containers.ContainerCliError,
    ) as e:
        con.error(str(e))
        raise typer.Exit(1) from e
    except PermissionError as e:
        con.error(f"Permission denied: {e}")
        raise typer.Exit(1) from e
