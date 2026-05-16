import json
import logging
import shutil
import tempfile
import tomllib
from pathlib import Path
from typing import TypedDict

log = logging.getLogger(__name__)


class TemplateNotFound(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Template '{name}' not found")


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
    description: str
    author: str


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

    def _load_capsule_toml(self, name: str) -> dict:
        p = self._dest(name) / self._PROVENANCE_FILE
        if not p.exists():
            return {}
        try:
            with p.open("rb") as f:
                return dict(tomllib.load(f))
        except (OSError, tomllib.TOMLDecodeError):
            log.warning("Could not read %s", p)
            return {}

    def _save_capsule_toml(self, name: str, data: dict) -> None:
        lines: list[str] = []
        for k, v in data.items():
            if k != "meta":
                lines.append(f'{k} = "{v}"')
        if meta := data.get("meta"):
            lines.append("")
            lines.append("[meta]")
            for k, v in meta.items():
                lines.append(f'{k} = "{v}"')
        (self._dest(name) / self._PROVENANCE_FILE).write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def list_templates(self) -> list[TemplateEntry]:
        result: list[TemplateEntry] = []
        for p in self._template_dirs():
            meta = self._load_capsule_toml(p.name).get("meta", {})
            result.append(
                {
                    "name": p.name,
                    "path": str(p),
                    "mtime": p.stat().st_mtime,
                    "description": str(meta.get("description", "")),
                    "author": str(meta.get("author", "")),
                }
            )
        return result

    def add(self, source: Path, name: str) -> Path:
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(
                f"Source path does not exist or is not a directory: {source}"
            )
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
            raise TemplateNotFound(name)
        shutil.rmtree(dest)
        log.info("Deleted template '%s'", name)

    def rename(self, old_name: str, new_name: str) -> None:
        src = self._dest(old_name)
        if not src.exists():
            raise TemplateNotFound(old_name)
        dst = self._dest(new_name)
        if dst.exists():
            raise TemplateAlreadyExists(f"Template '{new_name}' already exists")
        src.rename(dst)
        log.info("Renamed template '%s' to '%s'", old_name, new_name)

    def update(self, name: str, source: Path) -> None:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(name)
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(
                f"Source path does not exist or is not a directory: {source}"
            )
        new_json = source / "devcontainer.json"
        if not new_json.exists():
            raise MissingDevcontainer(f"No devcontainer.json found in {source}")
        self._validate_json(new_json)
        # Copy to a temp dir first so the dest is never left in a partial state.
        tmp = Path(tempfile.mkdtemp(dir=self._dir, prefix=f".{name}."))
        try:
            shutil.copytree(source, tmp, dirs_exist_ok=True)
            shutil.rmtree(dest)
            tmp.rename(dest)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        log.info("Updated template '%s' from %s", name, source)

    def view(self, name: str) -> tuple[str, Path]:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(name)
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
                data: object = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                log.warning("Skipping template '%s' in search: invalid JSON: %s", p.name, e)
                continue
            for field, snippet in self._flatten(data):
                if kw in field.lower() or kw in snippet.lower():
                    results.append(
                        {"template": p.name, "field": field, "snippet": snippet[:80]}
                    )
        return results

    def init(self, name: str, dest: Path, force: bool = False) -> Path:
        src = self._dest(name)
        if not src.exists():
            raise TemplateNotFound(name)
        if dest.exists():
            if not force:
                raise FileExistsError(f"{dest} already exists")
            tmp = dest.parent / f".{dest.name}.tmp"
            try:
                shutil.copytree(src, tmp)
                shutil.rmtree(dest)
                tmp.rename(dest)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise
        else:
            shutil.copytree(src, dest)
        log.info("Initialized template '%s' at %s", name, dest)
        return dest

    def export(self, name: str, output: Path) -> Path:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(name)
        base = str(output / name)
        shutil.make_archive(base, "zip", root_dir=self._dir, base_dir=name)
        result = Path(base + ".zip")
        log.info("Exported template '%s' to %s", name, result)
        return result

    def save_provenance(
        self, name: str, url: str, ref: str | None, subpath: str | None
    ) -> None:
        data = self._load_capsule_toml(name)
        data["url"] = url
        if ref:
            data["ref"] = ref
        elif "ref" in data:
            del data["ref"]
        if subpath:
            data["subpath"] = subpath
        elif "subpath" in data:
            del data["subpath"]
        self._save_capsule_toml(name, data)

    def load_provenance(self, name: str) -> dict[str, str]:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(name)
        p = dest / self._PROVENANCE_FILE
        if not p.exists():
            raise NoProvenance(
                f"Template '{name}' has no recorded source (was added from a local path)"
            )
        data = self._load_capsule_toml(name)
        if "url" not in data:
            raise NoProvenance(
                f"Template '{name}' has no recorded source (was added from a local path)"
            )
        return {k: str(v) for k, v in data.items() if k != "meta"}

    def load_meta(self, name: str) -> dict[str, str]:
        data = self._load_capsule_toml(name)
        return {k: str(v) for k, v in data.get("meta", {}).items()}

    def save_meta(
        self, name: str, description: str | None, author: str | None
    ) -> None:
        if not self._dest(name).exists():
            raise TemplateNotFound(name)
        data = self._load_capsule_toml(name)
        meta = dict(data.get("meta", {}))
        if description is not None:
            meta["description"] = description
        if author is not None:
            meta["author"] = author
        if meta:
            data["meta"] = meta
        self._save_capsule_toml(name, data)

    def _validate_json(self, path: Path) -> None:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise InvalidJSON(f"Invalid JSON in {path}: {e}") from e

    @staticmethod
    def _flatten(obj: object, prefix: str = "") -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                pairs.extend(TemplateStore._flatten(v, key))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                pairs.extend(TemplateStore._flatten(v, f"{prefix}[{i}]"))
        else:
            pairs.append((prefix, str(obj)))
        return pairs
