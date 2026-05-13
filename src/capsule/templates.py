import json
import logging
import shutil
import tomllib
from pathlib import Path
from typing import TypedDict, cast

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


class TemplateEntry(TypedDict):
    name: str
    path: str
    mtime: float


class SearchResult(TypedDict):
    template: str
    field: str
    snippet: str


class TemplateStore:
    _PROVENANCE_FILE = "capsule.toml"

    def __init__(self, store_dir: Path) -> None:
        self._dir = store_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _dest(self, name: str) -> Path:
        return self._dir / name

    def _template_dirs(self) -> list[Path]:
        return [p for p in sorted(self._dir.iterdir()) if p.is_dir()]

    def list_templates(self) -> list[TemplateEntry]:
        return [
            {"name": p.name, "path": str(p), "mtime": p.stat().st_mtime}
            for p in self._template_dirs()
        ]

    def add(self, source: Path, name: str) -> Path:
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(f"Source path does not exist or is not a directory: {source}")
        if not (source / "devcontainer.json").exists():
            raise MissingDevcontainer(f"No devcontainer.json found in {source}")
        dest = self._dest(name)
        if dest.exists():
            raise TemplateAlreadyExists(f"Template '{name}' already exists")
        self._validate_json(source / "devcontainer.json")
        shutil.copytree(source, dest)
        log.info("Added template '%s' from %s", name, source)
        return dest

    def delete(self, name: str) -> None:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(f"Template '{name}' not found")
        shutil.rmtree(dest)
        log.info("Deleted template '%s'", name)

    def rename(self, old_name: str, new_name: str) -> None:
        src = self._dest(old_name)
        if not src.exists():
            raise TemplateNotFound(f"Template '{old_name}' not found")
        dst = self._dest(new_name)
        if dst.exists():
            raise TemplateAlreadyExists(f"Template '{new_name}' already exists")
        src.rename(dst)
        log.info("Renamed template '%s' to '%s'", old_name, new_name)

    def update(self, name: str, source: Path) -> None:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(f"Template '{name}' not found")
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(f"Source path does not exist or is not a directory: {source}")
        new_json = source / "devcontainer.json"
        if not new_json.exists():
            raise MissingDevcontainer(f"No devcontainer.json found in {source}")
        self._validate_json(new_json)
        shutil.rmtree(dest)
        shutil.copytree(source, dest)
        log.info("Updated template '%s' from %s", name, source)

    def view(self, name: str) -> tuple[str, Path]:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(f"Template '{name}' not found")
        json_path = dest / "devcontainer.json"
        return json_path.read_text(encoding="utf-8"), json_path

    def search(self, keyword: str) -> list[SearchResult]:
        kw = keyword.lower()
        results: list[SearchResult] = []
        for p in self._template_dirs():
            json_path = p / "devcontainer.json"
            if not json_path.exists():
                continue
            try:
                data = cast(object, json.loads(json_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
            for field, snippet in self._flatten(data):
                if kw in field.lower() or kw in snippet.lower():
                    results.append({"template": p.name, "field": field, "snippet": snippet[:80]})
        return results

    def init(self, name: str, dest: Path, force: bool = False) -> Path:
        src = self._dest(name)
        if not src.exists():
            raise TemplateNotFound(f"Template '{name}' not found")
        if dest.exists():
            if not force:
                raise FileExistsError(f"{dest} already exists")
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        log.info("Initialized template '%s' at %s", name, dest)
        return dest

    def export(self, name: str, output: Path) -> Path:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(f"Template '{name}' not found")
        base = str(output / name)
        shutil.make_archive(base, "zip", root_dir=self._dir, base_dir=name)
        result = Path(base + ".zip")
        log.info("Exported template '%s' to %s", name, result)
        return result

    def save_provenance(self, name: str, url: str, ref: str | None, subpath: str | None) -> None:
        lines = [f'url = "{url}"']
        if ref:
            lines.append(f'ref = "{ref}"')
        if subpath:
            lines.append(f'subpath = "{subpath}"')
        (self._dest(name) / self._PROVENANCE_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def load_provenance(self, name: str) -> dict[str, str]:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(f"Template '{name}' not found")
        p = dest / self._PROVENANCE_FILE
        if not p.exists():
            raise NoProvenance(f"Template '{name}' has no recorded source (was added from a local path)")
        with p.open("rb") as f:
            return tomllib.load(f)  # type: ignore[return-value]

    def _validate_json(self, path: Path) -> None:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise InvalidJSON(f"Invalid JSON in {path}: {e}") from e

    @staticmethod
    def _flatten(obj: object, prefix: str = "") -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if isinstance(obj, dict):
            for k, v in cast(dict[str, object], obj).items():
                key = f"{prefix}.{k}" if prefix else k
                pairs.extend(TemplateStore._flatten(v, key))
        elif isinstance(obj, list):
            for i, v in enumerate(cast(list[object], obj)):
                pairs.extend(TemplateStore._flatten(v, f"{prefix}[{i}]"))
        else:
            pairs.append((prefix, str(obj)))
        return pairs
