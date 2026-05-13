import json
import logging
import shutil
import tomllib
from pathlib import Path
from typing import TypedDict, cast

from capsule.config import TEMPLATES_DIR

log = logging.getLogger(__name__)


class TemplateNotFound(Exception):
    pass


class TemplateAlreadyExists(Exception):
    pass


class InvalidJSON(Exception):
    pass


class MissingDevcontainer(Exception):
    pass


class NoProvenance(Exception):
    pass


_PROVENANCE_FILE = "capsule.toml"


class TemplateEntry(TypedDict):
    name: str
    path: str
    mtime: float


class SearchResult(TypedDict):
    template: str
    field: str
    snippet: str


def _template_dirs() -> list[Path]:
    return [p for p in sorted(TEMPLATES_DIR.iterdir()) if p.is_dir()]


def list_templates() -> list[TemplateEntry]:
    return [
        {"name": p.name, "path": str(p), "mtime": p.stat().st_mtime}
        for p in _template_dirs()
    ]


def _dest(name: str) -> Path:
    return TEMPLATES_DIR / name


def add_template(source: Path, name: str) -> Path:
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(
            f"Source path does not exist or is not a directory: {source}"
        )
    if not (source / "devcontainer.json").exists():
        raise MissingDevcontainer(f"No devcontainer.json found in {source}")
    dest = _dest(name)
    if dest.exists():
        raise TemplateAlreadyExists(f"Template '{name}' already exists")
    _validate_json(source / "devcontainer.json")
    _ = shutil.copytree(source, dest)
    log.info("Added template '%s' from %s", name, source)
    return dest


def delete_template(name: str) -> None:
    dest = _dest(name)
    if not dest.exists():
        raise TemplateNotFound(f"Template '{name}' not found")
    shutil.rmtree(dest)
    log.info("Deleted template '%s'", name)


def update_template(name: str, source: Path) -> None:
    dest = _dest(name)
    if not dest.exists():
        raise TemplateNotFound(f"Template '{name}' not found")
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(
            f"Source path does not exist or is not a directory: {source}"
        )
    new_json = source / "devcontainer.json"
    if not new_json.exists():
        raise MissingDevcontainer(f"No devcontainer.json found in {source}")
    _validate_json(new_json)
    shutil.rmtree(dest)
    _ = shutil.copytree(source, dest)
    log.info("Updated template '%s' from %s", name, source)


def view_template(name: str) -> tuple[str, Path]:
    dest = _dest(name)
    if not dest.exists():
        raise TemplateNotFound(f"Template '{name}' not found")
    json_path = dest / "devcontainer.json"
    return json_path.read_text(encoding="utf-8"), json_path


def search_templates(keyword: str) -> list[SearchResult]:
    kw = keyword.lower()
    results: list[SearchResult] = []
    for p in _template_dirs():
        json_path = p / "devcontainer.json"
        if not json_path.exists():
            continue
        try:
            data = cast(object, json.loads(json_path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
        for field, snippet in _flatten(data):
            if kw in field.lower() or kw in snippet.lower():
                results.append(
                    {
                        "template": p.name,
                        "field": field,
                        "snippet": snippet[:80],
                    }
                )
    return results


def init_template(name: str, dest: Path, force: bool = False) -> Path:
    src = _dest(name)
    if not src.exists():
        raise TemplateNotFound(f"Template '{name}' not found")
    if dest.exists():
        if not force:
            raise FileExistsError(f"{dest} already exists")
        shutil.rmtree(dest)
    _ = shutil.copytree(src, dest)
    log.info("Initialized template '%s' at %s", name, dest)
    return dest


def export_template(name: str, output: Path) -> Path:
    dest = _dest(name)
    if not dest.exists():
        raise TemplateNotFound(f"Template '{name}' not found")
    base = str(output / name)
    _ = shutil.make_archive(base, "zip", root_dir=TEMPLATES_DIR, base_dir=name)
    result = Path(base + ".zip")
    log.info("Exported template '%s' to %s", name, result)
    return result


def _validate_json(path: Path) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InvalidJSON(f"Invalid JSON in {path}: {e}") from e


def rename_template(old_name: str, new_name: str) -> None:
    src = _dest(old_name)
    if not src.exists():
        raise TemplateNotFound(f"Template '{old_name}' not found")
    dst = _dest(new_name)
    if dst.exists():
        raise TemplateAlreadyExists(f"Template '{new_name}' already exists")
    src.rename(dst)
    log.info("Renamed template '%s' to '%s'", old_name, new_name)


def save_provenance(name: str, url: str, ref: str | None, subpath: str | None) -> None:
    lines = [f'url = "{url}"']
    if ref:
        lines.append(f'ref = "{ref}"')
    if subpath:
        lines.append(f'subpath = "{subpath}"')
    (_dest(name) / _PROVENANCE_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_provenance(name: str) -> dict[str, str]:
    dest = _dest(name)
    if not dest.exists():
        raise TemplateNotFound(f"Template '{name}' not found")
    p = dest / _PROVENANCE_FILE
    if not p.exists():
        raise NoProvenance(f"Template '{name}' has no recorded source (was added from a local path)")
    with open(p, "rb") as f:
        return tomllib.load(f)  # type: ignore[return-value]


def _flatten(obj: object, prefix: str = "") -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in cast(dict[str, object], obj).items():
            key = f"{prefix}.{k}" if prefix else k
            pairs.extend(_flatten(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(cast(list[object], obj)):
            pairs.extend(_flatten(v, f"{prefix}[{i}]"))
    else:
        pairs.append((prefix, str(obj)))
    return pairs
