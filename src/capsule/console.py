import logging

from rich.console import Console
from rich.panel import Panel

console = Console()
log = logging.getLogger(__name__)


def error(msg: str, hint: str | None = None) -> None:
    log.error(msg)
    body = msg if hint is None else f"{msg}\n\n[dim]{hint}[/dim]"
    console.print(Panel(body, title="Error", border_style="red", title_align="left"))


def success(msg: str) -> None:
    console.print(Panel(msg, border_style="green"))


def info(msg: str) -> None:
    console.print(f"[blue]{msg}[/blue]")
