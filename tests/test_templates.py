import json
from pathlib import Path

import pytest

from capsule.templates import (
    InvalidJSON,
    MissingDevcontainer,
    NoProvenance,
    TemplateAlreadyExists,
    TemplateNotFound,
    TemplateStore,
)


def _make_template(base: Path, name: str, content: str | None = None) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "devcontainer.json").write_text(content or f'{{"name": "{name}"}}')
    return d


@pytest.fixture
def store(tmp_path: Path) -> TemplateStore:
    return TemplateStore(tmp_path / "store")


# -- add --

def test_add_success(store: TemplateStore, tmp_path: Path) -> None:
    src = _make_template(tmp_path, "python")
    dest = store.add(src, "python")
    assert dest.is_dir()
    assert (dest / "devcontainer.json").exists()


def test_add_invalid_json(store: TemplateStore, tmp_path: Path) -> None:
    src = _make_template(tmp_path, "python", "{bad json")
    with pytest.raises(InvalidJSON):
        store.add(src, "python")


def test_add_missing_devcontainer(store: TemplateStore, tmp_path: Path) -> None:
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(MissingDevcontainer):
        store.add(d, "empty")


def test_add_missing_source(store: TemplateStore, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        store.add(tmp_path / "nonexistent", "foo")


def test_add_duplicate(store: TemplateStore, tmp_path: Path) -> None:
    src = _make_template(tmp_path, "python")
    store.add(src, "python")
    with pytest.raises(TemplateAlreadyExists):
        store.add(src, "python")


# -- delete --

def test_delete_success(store: TemplateStore, tmp_path: Path) -> None:
    src = _make_template(tmp_path, "python")
    store.add(src, "python")
    store.delete("python")
    assert not (store._dir / "python").exists()


def test_delete_not_found(store: TemplateStore) -> None:
    with pytest.raises(TemplateNotFound):
        store.delete("nonexistent")


# -- rename --

def test_rename_success(store: TemplateStore, tmp_path: Path) -> None:
    src = _make_template(tmp_path, "python")
    store.add(src, "python")
    store.rename("python", "py")
    assert (store._dir / "py").is_dir()
    assert not (store._dir / "python").exists()


def test_rename_not_found(store: TemplateStore) -> None:
    with pytest.raises(TemplateNotFound):
        store.rename("nonexistent", "new")


def test_rename_conflicts(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path / "a", "python"), "python")
    store.add(_make_template(tmp_path / "b", "py"), "py")
    with pytest.raises(TemplateAlreadyExists):
        store.rename("python", "py")


# -- update --

def test_update_replaces_content(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path / "orig", "python", '{"name": "orig"}'), "python")
    store.update("python", _make_template(tmp_path / "new", "python", '{"name": "new"}'))
    raw, _ = store.view("python")
    assert json.loads(raw)["name"] == "new"


def test_update_not_found(store: TemplateStore, tmp_path: Path) -> None:
    src = _make_template(tmp_path, "python")
    with pytest.raises(TemplateNotFound):
        store.update("nonexistent", src)


def test_update_invalid_json(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path / "orig", "python"), "python")
    with pytest.raises(InvalidJSON):
        store.update("python", _make_template(tmp_path / "bad", "python", "{bad}"))


def test_update_preserves_template_on_invalid_json(
    store: TemplateStore, tmp_path: Path
) -> None:
    """Atomic update: old template must survive a failed update."""
    store.add(_make_template(tmp_path / "orig", "python", '{"name": "original"}'), "python")
    with pytest.raises(InvalidJSON):
        store.update("python", _make_template(tmp_path / "bad", "python", "{bad}"))
    raw, _ = store.view("python")
    assert json.loads(raw)["name"] == "original"


# -- export --

def test_export_creates_zip(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    result = store.export("python", tmp_path)
    assert result.suffix == ".zip"
    assert result.exists()


def test_export_not_found(store: TemplateStore, tmp_path: Path) -> None:
    with pytest.raises(TemplateNotFound):
        store.export("nonexistent", tmp_path)


# -- init --

def test_init_copies_to_dest(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path / "src", "python"), "python")
    dest = tmp_path / ".devcontainer"
    result = store.init("python", dest)
    assert result == dest
    assert (dest / "devcontainer.json").exists()


def test_init_raises_if_exists(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path / "src", "python"), "python")
    dest = tmp_path / ".devcontainer"
    dest.mkdir()
    with pytest.raises(FileExistsError):
        store.init("python", dest)


def test_init_force_overwrites(store: TemplateStore, tmp_path: Path) -> None:
    store.add(
        _make_template(tmp_path / "src", "python", '{"name": "new"}'), "python"
    )
    dest = tmp_path / ".devcontainer"
    dest.mkdir()
    (dest / "devcontainer.json").write_text('{"name": "old"}')
    store.init("python", dest, force=True)
    assert json.loads((dest / "devcontainer.json").read_text())["name"] == "new"


# -- search --

def test_search_finds_keyword(store: TemplateStore, tmp_path: Path) -> None:
    store.add(
        _make_template(tmp_path, "python", '{"image": "mcr.microsoft.com/python:3.11"}'),
        "python",
    )
    results = store.search("python")
    assert any(r["template"] == "python" for r in results)


def test_search_no_matches(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "node", '{"image": "node:18"}'), "node")
    assert store.search("rust") == []


def test_search_case_insensitive(store: TemplateStore, tmp_path: Path) -> None:
    store.add(
        _make_template(tmp_path, "python", '{"image": "Python:latest"}'), "python"
    )
    assert any(r["template"] == "python" for r in store.search("python"))


# -- provenance --

def test_save_and_load_provenance(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    store.save_provenance("python", "https://github.com/x/y.git", "main", "templates/python")
    data = store.load_provenance("python")
    assert data["url"] == "https://github.com/x/y.git"
    assert data["ref"] == "main"
    assert data["subpath"] == "templates/python"


def test_load_provenance_not_found(store: TemplateStore) -> None:
    with pytest.raises(TemplateNotFound):
        store.load_provenance("nonexistent")


def test_load_provenance_no_source(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    with pytest.raises(NoProvenance):
        store.load_provenance("python")


# -- meta --

def test_save_and_load_meta(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    store.save_meta("python", description="Python dev env", author="Alice")
    meta = store.load_meta("python")
    assert meta["description"] == "Python dev env"
    assert meta["author"] == "Alice"


def test_save_meta_partial_update(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    store.save_meta("python", description="desc", author="Alice")
    store.save_meta("python", description="new desc", author=None)
    meta = store.load_meta("python")
    assert meta["description"] == "new desc"
    assert meta["author"] == "Alice"


def test_meta_preserved_when_provenance_resaved(
    store: TemplateStore, tmp_path: Path
) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    store.save_provenance("python", "https://github.com/x/y.git", "main", None)
    store.save_meta("python", description="desc", author=None)
    store.save_provenance("python", "https://github.com/x/y.git", "v2", None)
    assert store.load_meta("python")["description"] == "desc"
    assert store.load_provenance("python")["ref"] == "v2"


def test_meta_not_in_provenance(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    store.save_provenance("python", "https://github.com/x/y.git", None, None)
    store.save_meta("python", description="desc", author=None)
    data = store.load_provenance("python")
    assert "meta" not in data


def test_meta_in_list_templates(store: TemplateStore, tmp_path: Path) -> None:
    store.add(_make_template(tmp_path, "python"), "python")
    store.save_meta("python", description="Python dev env", author=None)
    entries = store.list_templates()
    entry = next(e for e in entries if e["name"] == "python")
    assert entry["description"] == "Python dev env"
    assert entry["author"] == ""


def test_save_meta_not_found(store: TemplateStore) -> None:
    with pytest.raises(TemplateNotFound):
        store.save_meta("nonexistent", description="x", author=None)
