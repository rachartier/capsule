import json
from pathlib import Path

import pytest

from capsule.app import _add_all_templates
from capsule.config import TEMPLATES_DIR


def _make_template(base: Path, name: str, valid_json: bool = True) -> Path:
    d = base / name
    d.mkdir()
    content = '{"name": "%s"}' % name if valid_json else "{bad json"
    (d / "devcontainer.json").write_text(content)
    return d


@pytest.fixture(autouse=True)
def isolated_templates(tmp_path, monkeypatch):
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setattr("capsule.templates.TEMPLATES_DIR", store)
    monkeypatch.setattr("capsule.app.TEMPLATES_DIR", store, raising=False)
    return store


def test_add_all_happy_path(tmp_path, isolated_templates):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    _make_template(src, "rust")

    had_errors = _add_all_templates(src)

    assert not had_errors
    assert (isolated_templates / "python").is_dir()
    assert (isolated_templates / "rust").is_dir()


def test_add_all_skips_conflict(tmp_path, isolated_templates):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    _make_template(src, "node")

    (isolated_templates / "python").mkdir()
    (isolated_templates / "python" / "devcontainer.json").write_text('{"name":"python"}')

    had_errors = _add_all_templates(src)

    assert not had_errors
    assert (isolated_templates / "node").is_dir()


def test_add_all_conflict_only(tmp_path, isolated_templates):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")

    (isolated_templates / "python").mkdir()
    (isolated_templates / "python" / "devcontainer.json").write_text('{"name":"python"}')

    had_errors = _add_all_templates(src)

    assert not had_errors


def test_add_all_no_candidates(tmp_path):
    src = tmp_path / "empty"
    src.mkdir()

    had_errors = _add_all_templates(src)

    assert had_errors


def test_add_all_invalid_json_is_hard_error(tmp_path, isolated_templates):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    _make_template(src, "broken", valid_json=False)

    had_errors = _add_all_templates(src)

    assert had_errors
    assert (isolated_templates / "python").is_dir()


def test_add_all_ignores_files(tmp_path, isolated_templates):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    (src / "README.md").write_text("hello")

    had_errors = _add_all_templates(src)

    assert not had_errors
    assert (isolated_templates / "python").is_dir()


def test_add_all_ignores_dirs_without_devcontainer(tmp_path, isolated_templates):
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    (src / "not-a-template").mkdir()

    had_errors = _add_all_templates(src)

    assert not had_errors
    assert not (isolated_templates / "not-a-template").exists()
