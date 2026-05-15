import contextlib
import itertools
import logging
import os
import re
import select
import sys
import termios
import tty

from rich import box
from rich.console import Console, Group
from rich.json import JSON
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

log = logging.getLogger(__name__)
_console = Console(highlight=False)

# Matches ANSI/VT100 escape sequences (CSI, OSC with BEL or ST terminator, two-char escapes).
_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[^[])")


def _clean(line: str) -> str:
    # \r is used by progress bars to overwrite the current line; keep the last segment.
    return _ANSI_RE.sub("", line.rsplit("\r", 1)[-1])


def error(msg: str, hint: str | None = None) -> None:
    log.error(msg)
    _console.print(f"[bold red]![/] {msg}")
    if hint:
        _console.print(f"  [dim]{hint}[/]")


def success(msg: str) -> None:
    _console.print(f"[bold green]✓[/] {msg}")


def info(msg: str) -> None:
    _console.print(f"[cyan]*[/] {msg}")


def confirm(msg: str) -> bool:
    try:
        return Confirm.ask(msg, default=False, console=_console)
    except (EOFError, KeyboardInterrupt):
        _console.print()
        return False


def spinner(label: str):
    return _console.status(label, spinner="dots")


@contextlib.contextmanager
def launching(label: str, quiet: bool):
    _spinner = Spinner("dots", text=f" {label}", style="cyan")
    with Live(_spinner, auto_refresh=True, console=_console, transient=True, refresh_per_second=12.5):
        def _on_line(line: str) -> None:
            if not quiet:
                clean = _clean(line)
                if clean:
                    _console.print(f"  [dim]{escape(clean)}[/]")
        yield _on_line


def _read_key() -> str:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        # os.read bypasses Python's BufferedReader: sys.stdin.read(1) would consume
        # the full escape sequence in one OS read(), leaving the kernel buffer empty
        # so select.select() finds nothing and arrow keys collapse to bare \x1b.
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                ch += os.read(fd, 8)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch.decode("utf-8", errors="replace")


def pick(options: list[str]) -> str | None:
    if not options:
        return None
    if len(options) == 1:
        return options[0]

    query = ""
    sel = 0
    total = len(options)

    def _filtered() -> list[tuple[str, list[int] | None]]:
        if not query:
            return [(o, None) for o in options]
        matched = [
            (o, pos) for o in options if (pos := _fuzzy_positions(query, o)) is not None
        ]
        matched.sort(key=lambda x: _match_score(x[1]))  # type: ignore[arg-type]
        return matched

    def _render(items: list[tuple[str, list[int] | None]]) -> Group:
        lines: list = [
            Text.from_markup(f"  [cyan]>[/] {escape(query)}[blink]▌[/]"),
            Rule(style="dim"),
        ]
        for i, (opt, positions) in enumerate(items):
            label = _highlight_matches(opt, positions) if positions else escape(opt)
            if i == sel:
                lines.append(Text.from_markup(f"  [bold cyan]▶[/]  {label}"))
            else:
                lines.append(Text.from_markup(f"     {label}"))
        n = len(items)
        suffix = (
            f"[dim]{n} of {total}[/]"
            if n != total
            else f"[dim]{total} template{'s' if total != 1 else ''}[/]"
        )
        lines.append(Text.from_markup(f"\n  {suffix}"))
        return Group(*lines)

    with Live(
        _render(_filtered()), console=_console, auto_refresh=False, transient=True
    ) as live:
        while True:
            items = _filtered()
            sel = min(sel, max(len(items) - 1, 0))
            live.update(_render(items), refresh=True)
            key = _read_key()
            if key in ("\r", "\n"):
                return items[sel][0] if items else None
            if key in ("\x03", "\x1b"):
                return None
            if key == "\x1b[A":
                sel = max(0, sel - 1)
            elif key == "\x1b[B":
                sel = min(len(items) - 1, sel + 1) if items else 0
            elif key == "\x7f":
                query = query[:-1]
                sel = 0
            elif key.isprintable():
                query += key
                sel = 0


def _fuzzy_positions(query: str, target: str) -> list[int] | None:
    positions: list[int] = []
    qi = 0
    q = query.lower()
    for ti, c in enumerate(target.lower()):
        if c == q[qi]:
            positions.append(ti)
            qi += 1
            if qi == len(q):
                return positions
    return None


def _match_score(positions: list[int]) -> tuple[int, int]:
    consecutive = sum(1 for a, b in itertools.pairwise(positions) if b == a + 1)
    return (positions[0], -consecutive)


def _highlight_matches(target: str, positions: list[int]) -> str:
    pos_set = set(positions)
    parts: list[str] = []
    in_match = False
    for i, c in enumerate(target):
        is_match = i in pos_set
        if is_match and not in_match:
            parts.append("[bold]")
            in_match = True
        elif not is_match and in_match:
            parts.append("[/bold]")
            in_match = False
        parts.append(escape(c))
    if in_match:
        parts.append("[/bold]")
    return "".join(parts)


def subprocess_output(text: str) -> None:
    for line in text.splitlines():
        clean = _clean(line)
        if clean:
            _console.print(f"{escape(clean)}")


def print_table(headers: list[str], rows: list[list[str]]) -> None:
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


def print_json(raw: str, title: str) -> None:
    _console.print(Panel(JSON(raw), title=f"[dim]{title}[/]", border_style="dim blue"))
