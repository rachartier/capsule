import json as _json
import logging
import sys

log = logging.getLogger(__name__)

_RST = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GRN = "\033[32m"
_BLU = "\033[34m"


def _tty() -> bool:
    return sys.stdout.isatty()


def _c(*codes: str, text: str) -> str:
    return ("".join(codes) + text + _RST) if _tty() else text


def error(msg: str, hint: str | None = None) -> None:
    log.error(msg)
    print(_c(_BOLD, _RED, text="!") + " " + msg)
    if hint:
        print("  " + _c(_DIM, text=hint))


def success(msg: str) -> None:
    print(_c(_BOLD, _GRN, text="✓") + " " + msg)


def info(msg: str) -> None:
    print(_c(_BLU, text="*") + " " + msg)


def confirm(msg: str) -> bool:
    try:
        return input(f"{msg} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def _row(cells: list[str], bold: bool = False) -> str:
        line = "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))
        return _c(_BOLD, _BLU, text=line) if bold else line

    print(_row(headers, bold=True))
    print(_c(_DIM, text="  ".join("-" * w for w in widths)))
    for row in rows:
        print(_row(row))


def print_json(raw: str, title: str) -> None:
    bar = "--- " + title
    print(_c(_BLU, text=bar))
    obj = _json.loads(raw)
    for line in _json.dumps(obj, indent=2).splitlines():
        print(line)
    print()
