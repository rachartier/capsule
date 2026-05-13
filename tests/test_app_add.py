from pathlib import Path

import pytest

from capsule.app import _add_all_templates
from capsule.templates import TemplateStore


def _make_template(base: Path, name: str, valid_json: bool = True) -> Path:
    d = base / name
    d.mkdir()
    content = f'{{"name": "{name}"}}' if valid_json else "{bad json"
    (d / "devcontainer.json").write_text(content)
    return d


@pytest.fixture
def store(tmp_path) -> TemplateStore:
    return TemplateStore(tmp_path / "store")


def test_add_all_happy_path(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    _make_template(src, "rust")

    had_errors = _add_all_templates(src, store)

    assert not had_errors
    assert (store._dir / "python").is_dir()
    assert (store._dir / "rust").is_dir()


def test_add_all_skips_conflict(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    _make_template(src, "node")

    (store._dir / "python").mkdir()
    (store._dir / "python" / "devcontainer.json").write_text('{"name":"python"}')

    had_errors = _add_all_templates(src, store)

    assert not had_errors
    assert (store._dir / "node").is_dir()


def test_add_all_conflict_only(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")

    (store._dir / "python").mkdir()
    (store._dir / "python" / "devcontainer.json").write_text('{"name":"python"}')

    had_errors = _add_all_templates(src, store)

    assert not had_errors


def test_add_all_no_candidates(tmp_path, store):
    src = tmp_path / "empty"
    src.mkdir()

    had_errors = _add_all_templates(src, store)

    assert had_errors


def test_add_all_invalid_json_is_hard_error(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    _make_template(src, "broken", valid_json=False)

    had_errors = _add_all_templates(src, store)

    assert had_errors
    assert (store._dir / "python").is_dir()


def test_add_all_ignores_files(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    (src / "README.md").write_text("hello")

    had_errors = _add_all_templates(src, store)

    assert not had_errors
    assert (store._dir / "python").is_dir()


def test_add_all_ignores_dirs_without_devcontainer(tmp_path, store):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    (src / "not-a-template").mkdir()

    had_errors = _add_all_templates(src, store)

    assert not had_errors
    assert not (store._dir / "not-a-template").exists()
