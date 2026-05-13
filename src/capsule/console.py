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


_IS_TTY: bool = sys.stdout.isatty()


def _c(*codes: str, text: str) -> str:
    return ("".join(codes) + text + _RST) if _IS_TTY else text


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


def _fuzzy_match(query: str, target: str) -> bool:
    it = iter(target.lower())
    return all(c in it for c in query.lower())


def pick(options: list[str]) -> str | None:
    if not options:
        return None
    current = list(options)
    while True:
        for i, opt in enumerate(current, 1):
            print(f"  {_c(_BOLD, _BLU, text=str(i).rjust(2))}  {opt}")
        try:
            raw = input("Select number or filter: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if not raw:
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(current):
            return current[int(raw) - 1]
        filtered = [o for o in options if _fuzzy_match(raw, o)]
        if not filtered:
            info(f"No matches for '{raw}'.")
        elif len(filtered) == 1:
            return filtered[0]
        else:
            current = filtered


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
