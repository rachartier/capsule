"""Terminal output: status messages, prompts, spinners and tables."""

import contextlib
import logging
import re
from collections.abc import Callable, Generator, Sequence

from rich import box
from rich.console import Console
from rich.json import JSON
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt
from rich.spinner import Spinner
from rich.status import Status
from rich.table import Table

log = logging.getLogger(__name__)
_console = Console(highlight=False)

# Matches ANSI/VT100 escape sequences (CSI, OSC with BEL or ST terminator, two-char escapes).
_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[^[])")


def _clean(line: str) -> str:
    # \r is used by progress bars to overwrite the current line; keep the last segment.
    return _ANSI_RE.sub("", line.rsplit("\r", 1)[-1])


def error(msg: str, hint: str | None = None) -> None:
    """Logs and prints an error, followed by an optional hint."""
    log.error(msg)
    _console.print(f"[bold red]![/] {escape(msg)}")
    if hint:
        _console.print(f"  [dim]{escape(hint)}[/]")


def success(msg: str) -> None:
    """Prints a success message."""
    _console.print(f"[bold green]✓[/] {escape(msg)}")


def info(msg: str) -> None:
    """Prints an informational message."""
    _console.print(f"[cyan]*[/] {escape(msg)}")


def confirm(msg: str) -> bool:
    """Asks a yes/no question; returns False on no, EOF or Ctrl-C."""
    try:
        return Confirm.ask(msg, default=False, console=_console)
    except (EOFError, KeyboardInterrupt):
        _console.print()
        return False


def spinner(label: str) -> Status:
    """Returns a spinner to use as a context manager while work runs."""
    return _console.status(label, spinner="dots")


@contextlib.contextmanager
def launching(label: str, *, quiet: bool) -> Generator[Callable[[str], None]]:
    """Shows a spinner while a subprocess runs.

    Args:
        label: The text next to the spinner.
        quiet: Hide the spinner and the subprocess output.

    Yields:
        A function that prints one line of subprocess output, cleaned of
        terminal escape sequences.
    """
    if quiet:
        yield lambda _: None
        return

    with Live(
        Spinner("dots", text=f" {label}", style="cyan"),
        auto_refresh=True,
        console=_console,
        transient=True,
        refresh_per_second=12.5,
    ):

        def _on_line(line: str) -> None:
            clean = _clean(line)
            if clean:
                _console.print(f"  [dim]{escape(clean)}[/]")

        yield _on_line


def pick(options: Sequence[str]) -> str | None:
    """Asks the user to pick one option from a numbered list.

    Returns:
        The picked option, the only option when there is one, or None when
        there are none or the user aborts.
    """
    # ponytail: numbered prompt; bring back a fuzzy finder if template lists get long
    if not options:
        return None

    if len(options) == 1:
        return options[0]

    for i, opt in enumerate(options, 1):
        _console.print(f"  [cyan]{i}[/] {escape(opt)}")

    try:
        n = IntPrompt.ask(
            "Select",
            console=_console,
            choices=[str(i) for i in range(1, len(options) + 1)],
            show_choices=False,
        )
    except (EOFError, KeyboardInterrupt):
        _console.print()
        return None

    return options[n - 1]


def subprocess_output(text: str) -> None:
    """Prints captured subprocess output, cleaned of terminal escape sequences."""
    for line in text.splitlines():
        clean = _clean(line)
        if clean:
            _console.print(escape(clean))


def print_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """Prints rows as a table followed by the item count."""
    table = Table(
        box=box.ASCII,
        show_edge=False,
        pad_edge=False,
        header_style="bold blue",
    )
    for h in headers:
        table.add_column(h, overflow="fold")
    for row in rows:
        table.add_row(*row)

    _console.print(table)
    n = len(rows)
    _console.print(f"  [dim]{n} item{'s' if n != 1 else ''}[/]\n")


def print_template_header(name: str, description: str, author: str) -> None:
    """Prints a template's name, and its description and author when set."""
    pairs: list[tuple[str, str]] = [("Template", name)]
    if description:
        pairs.append(("Description", description))
    if author:
        pairs.append(("Author", author))

    width = max(len(k) for k, _ in pairs)
    for key, val in pairs:
        _console.print(f"[dim]{key:<{width}}[/]  {escape(val)}")
    _console.print()


def print_json(raw: str, title: str) -> None:
    """Pretty-prints a JSON document in a titled panel."""
    _console.print(Panel(JSON(raw), title=f"[dim]{title}[/]", border_style="dim blue"))
