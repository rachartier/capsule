"""The template store: one directory per template under the store root."""

import json
import logging
import shutil
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from capsule.sources import GitSource

log = logging.getLogger(__name__)

_STATE_FILE = "capsule.toml"


class TemplateNotFound(Exception):
    """A template name that is not in the store."""

    def __init__(self, name: str) -> None:
        """Initializes the error for the missing template `name`."""
        self.name = name
        super().__init__(f"Template '{name}' not found")


class TemplateAlreadyExists(Exception):
    """A template name that is already taken in the store."""


class InvalidJSON(Exception):
    """A devcontainer.json that is not valid JSON."""


class MissingDevcontainer(Exception):
    """A template directory without a devcontainer.json."""


class NoProvenance(Exception):
    """A template that was not added from a git source."""


@dataclass(frozen=True)
class TemplateEntry:
    """A stored template as shown in listings."""

    name: str
    path: Path
    mtime: float
    description: str
    author: str


@dataclass(frozen=True)
class SearchMatch:
    """A devcontainer.json field whose name or value matched a search."""

    template: str
    field: str
    snippet: str


@dataclass(frozen=True)
class RunOverride:
    """The per-template UID and GID that replace the global config's."""

    uid: int | None = None
    gid: int | None = None


def validate_json(path: Path) -> None:
    """Checks that a file holds valid JSON.

    Raises:
        InvalidJSON: The file is not valid JSON.
    """
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise InvalidJSON(f"Invalid JSON in {path}: {e}") from e


def _check_source_dir(source: Path) -> None:
    """Checks that `source` is a directory holding a valid devcontainer.json."""
    if not source.is_dir():
        raise FileNotFoundError(
            f"Source path does not exist or is not a directory: {source}"
        )

    json_path = source / "devcontainer.json"
    if not json_path.exists():
        raise MissingDevcontainer(f"No devcontainer.json found in {source}")

    validate_json(json_path)


def _flatten(obj: object, prefix: str = "") -> list[tuple[str, str]]:
    """Returns (dotted field path, value) pairs for every leaf of a JSON value."""
    if isinstance(obj, dict):
        return [
            pair
            for key, value in obj.items()
            for pair in _flatten(value, f"{prefix}.{key}" if prefix else key)
        ]

    if isinstance(obj, list):
        return [
            pair
            for i, value in enumerate(obj)
            for pair in _flatten(value, f"{prefix}[{i}]")
        ]

    return [(prefix, str(obj))]


def _toml_table(name: str | None, values: Mapping[str, object]) -> list[str]:
    lines = [f"[{name}]"] if name else []
    lines += [
        f"{key} = {value}" if isinstance(value, int) else f'{key} = "{value}"'
        for key, value in values.items()
    ]
    return lines


class TemplateStore:
    """A directory of templates, each a folder holding a devcontainer.json.

    Store-side state (git provenance, metadata, UID/GID override) lives in a
    capsule.toml next to each template's devcontainer.json.
    """

    def __init__(self, store_dir: Path) -> None:
        """Opens the store at `store_dir`, creating the directory if needed."""
        self._dir = store_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _dest(self, name: str) -> Path:
        return self._dir / name

    def _existing(self, name: str) -> Path:
        dest = self._dest(name)
        if not dest.exists():
            raise TemplateNotFound(name)

        return dest

    def _template_dirs(self) -> list[Path]:
        return [p for p in sorted(self._dir.iterdir()) if p.is_dir()]

    def _load_state(self, name: str) -> dict[str, object]:
        """Reads a template's capsule.toml; an unreadable file counts as empty, with a warning."""
        path = self._dest(name) / _STATE_FILE
        if not path.exists():
            return {}

        try:
            with path.open("rb") as f:
                return tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError):
            log.warning("Could not read %s", path)
            return {}

    def _save_state(self, name: str, data: Mapping[str, object]) -> None:
        top = {k: str(v) for k, v in data.items() if k not in ("meta", "run")}
        lines = _toml_table(None, top)
        for table in ("run", "meta"):
            values = data.get(table)
            if isinstance(values, dict) and values:
                lines += ["", *_toml_table(table, values)]

        (self._dest(name) / _STATE_FILE).write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def _section(self, name: str, table: str) -> dict[str, object]:
        section = self._load_state(name).get(table, {})
        return dict(section) if isinstance(section, dict) else {}

    def list_templates(self) -> list[TemplateEntry]:
        """Returns every stored template, sorted by name."""
        entries: list[TemplateEntry] = []
        for path in self._template_dirs():
            meta = self._section(path.name, "meta")
            entries.append(
                TemplateEntry(
                    name=path.name,
                    path=path,
                    mtime=path.stat().st_mtime,
                    description=str(meta.get("description", "")),
                    author=str(meta.get("author", "")),
                )
            )

        return entries

    def add(self, source: Path, name: str) -> Path:
        """Copies a template directory into the store.

        Returns:
            The stored template's directory.

        Raises:
            FileNotFoundError: `source` is not a directory.
            MissingDevcontainer: `source` has no devcontainer.json.
            InvalidJSON: Its devcontainer.json is not valid JSON.
            TemplateAlreadyExists: A template named `name` exists.
        """
        dest = self._dest(name)
        if dest.exists():
            raise TemplateAlreadyExists(f"Template '{name}' already exists")

        _check_source_dir(source)
        shutil.copytree(source, dest)
        log.info("Added template '%s' from %s", name, source)
        return dest

    def delete(self, name: str) -> None:
        """Removes a template from the store.

        Raises:
            TemplateNotFound: No template is named `name`.
        """
        shutil.rmtree(self._existing(name))
        log.info("Deleted template '%s'", name)

    def rename(self, old_name: str, new_name: str) -> None:
        """Renames a stored template.

        Raises:
            TemplateNotFound: No template is named `old_name`.
            TemplateAlreadyExists: A template named `new_name` exists.
        """
        src = self._existing(old_name)
        dst = self._dest(new_name)
        if dst.exists():
            raise TemplateAlreadyExists(f"Template '{new_name}' already exists")

        src.rename(dst)
        log.info("Renamed template '%s' to '%s'", old_name, new_name)

    def update(self, name: str, source: Path) -> None:
        """Replaces a template's files with those of `source`, keeping its capsule.toml.

        The template is left unchanged if the copy fails.

        Raises:
            TemplateNotFound: No template is named `name`.
            FileNotFoundError: `source` is not a directory.
            MissingDevcontainer: `source` has no devcontainer.json.
            InvalidJSON: Its devcontainer.json is not valid JSON.
        """
        dest = self._existing(name)
        _check_source_dir(source)

        # Copy to a temp dir first so the dest is never left in a partial state.
        tmp = Path(tempfile.mkdtemp(dir=self._dir, prefix=f".{name}."))
        try:
            shutil.copytree(source, tmp, dirs_exist_ok=True)
            state = dest / _STATE_FILE
            if state.exists():
                shutil.copy2(state, tmp / _STATE_FILE)
            shutil.rmtree(dest)
            tmp.rename(dest)
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

        log.info("Updated template '%s' from %s", name, source)

    def view(self, name: str) -> tuple[str, Path]:
        """Returns a template's devcontainer.json content and path.

        Raises:
            TemplateNotFound: No template is named `name`.
        """
        json_path = self._existing(name) / "devcontainer.json"
        return json_path.read_text(encoding="utf-8"), json_path

    def search(self, keyword: str) -> list[SearchMatch]:
        """Finds devcontainer.json fields whose path or value contains a keyword.

        The match ignores case. Templates with invalid JSON are skipped with
        a warning.

        Returns:
            The matches, with values cut to 80 characters.
        """
        kw = keyword.lower()
        matches: list[SearchMatch] = []
        for path in self._template_dirs():
            json_path = path / "devcontainer.json"
            if not json_path.exists():
                continue

            try:
                data: object = json.loads(json_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                log.warning(
                    "Skipping template '%s' in search: invalid JSON: %s", path.name, e
                )
                continue

            matches += [
                SearchMatch(template=path.name, field=field, snippet=snippet[:80])
                for field, snippet in _flatten(data)
                if kw in field.lower() or kw in snippet.lower()
            ]

        return matches

    def init(self, name: str, dest: Path, *, force: bool = False) -> Path:
        """Copies a template to `dest`.

        Args:
            name: The template to copy.
            dest: The directory to create.
            force: Replace `dest` if it exists. The old directory is kept if
                the copy fails.

        Returns:
            `dest`.

        Raises:
            TemplateNotFound: No template is named `name`.
            FileExistsError: `dest` exists and `force` is False.
        """
        src = self._existing(name)
        if not dest.exists():
            shutil.copytree(src, dest)
        elif not force:
            raise FileExistsError(f"{dest} already exists")
        else:
            tmp = dest.parent / f".{dest.name}.tmp"
            try:
                shutil.copytree(src, tmp)
                shutil.rmtree(dest)
                tmp.rename(dest)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)
                raise

        log.info("Initialized template '%s' at %s", name, dest)
        return dest

    def export(self, name: str, output: Path) -> Path:
        """Writes a template as `<output>/<name>.zip`.

        Returns:
            The archive's path.

        Raises:
            TemplateNotFound: No template is named `name`.
        """
        self._existing(name)

        archive = Path(
            shutil.make_archive(
                str(output / name), "zip", root_dir=self._dir, base_dir=name
            )
        )
        log.info("Exported template '%s' to %s", name, archive)
        return archive

    def save_provenance(self, name: str, source: GitSource) -> None:
        """Records the git source a template was fetched from, keeping its other state."""
        data = self._load_state(name)
        data["url"] = source.url
        for key, value in (("ref", source.ref), ("subpath", source.subpath)):
            if value:
                data[key] = value
            else:
                data.pop(key, None)

        self._save_state(name, data)

    def load_provenance(self, name: str) -> GitSource:
        """Returns the git source a template was fetched from.

        Raises:
            TemplateNotFound: No template is named `name`.
            NoProvenance: The template was added from a local path.
        """
        self._existing(name)

        data = self._load_state(name)
        if "url" not in data:
            raise NoProvenance(
                f"Template '{name}' has no recorded source (was added from a local path)"
            )

        ref = data.get("ref")
        subpath = data.get("subpath")
        return GitSource(
            url=str(data["url"]),
            ref=str(ref) if ref is not None else None,
            subpath=str(subpath) if subpath is not None else None,
        )

    def load_meta(self, name: str) -> dict[str, str]:
        """Returns a template's metadata (description, author) as set."""
        return {k: str(v) for k, v in self._section(name, "meta").items()}

    def save_meta(self, name: str, description: str | None, author: str | None) -> None:
        """Sets a template's description and author; None leaves a field as is.

        Raises:
            TemplateNotFound: No template is named `name`.
        """
        self._existing(name)

        data = self._load_state(name)
        meta = self._section(name, "meta")
        if description is not None:
            meta["description"] = description
        if author is not None:
            meta["author"] = author
        if meta:
            data["meta"] = meta

        self._save_state(name, data)

    def load_run_override(self, name: str) -> RunOverride:
        """Returns a template's UID/GID override; invalid values are ignored with a warning."""
        run = self._section(name, "run")
        ids: dict[str, int] = {}
        for key in ("uid", "gid"):
            value = run.get(key)
            if value is None:
                continue

            if isinstance(value, int) and not isinstance(value, bool):
                ids[key] = value
            else:
                log.warning(
                    "Template '%s': invalid %s in capsule.toml, ignoring", name, key
                )

        return RunOverride(uid=ids.get("uid"), gid=ids.get("gid"))

    def save_run_override(self, name: str, uid: int | None, gid: int | None) -> None:
        """Sets a template's UID/GID override; None removes that field.

        Raises:
            TemplateNotFound: No template is named `name`.
        """
        self._existing(name)

        data = self._load_state(name)
        run = {k: v for k, v in (("uid", uid), ("gid", gid)) if v is not None}
        if run:
            data["run"] = run
        else:
            data.pop("run", None)

        self._save_state(name, data)
