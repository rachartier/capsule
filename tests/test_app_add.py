import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from capsule import console as con
from capsule.app import app
from capsule.cli import context
from capsule.cli.add import _add_all_templates
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
    (store._dir / "python" / "devcontainer.json").write_text('{"name": "original"}')

    had_errors = _add_all_templates(src, store)

    assert not had_errors
    assert (store._dir / "node").is_dir()
    assert (
        json.loads((store._dir / "python" / "devcontainer.json").read_text())["name"]
        == "original"
    )


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


def test_add_help_shows_source_format() -> None:
    result = CliRunner().invoke(app, ["add", "--help"])
    assert result.exit_code == 0
    assert "gh:owner/repo[@ref][/subpath]" in result.output


def test_messages_print_brackets_literally(capsys: pytest.CaptureFixture[str]) -> None:
    con.error("Expected 'gh:owner/repo[@ref][/subpath]'.", "[/hint]")
    out = capsys.readouterr().out
    assert "[@ref][/subpath]" in out
    assert "[/hint]" in out


def test_add_invalid_shorthand_reports_error() -> None:
    result = CliRunner().invoke(app, ["add", "gh:foo"])
    assert result.exit_code == 1
    assert "Invalid gh: shorthand" in result.output


def test_add_local_template_under_given_name(
    tmp_path: Path, store: TemplateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(context, "store", store)
    src = _make_template(tmp_path, "src")
    result = CliRunner().invoke(app, ["add", str(src), "--name", "python"])
    assert result.exit_code == 0
    assert (store._dir / "python" / "devcontainer.json").exists()


def test_add_name_for_directory_of_templates_is_rejected(
    tmp_path: Path, store: TemplateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(context, "store", store)
    src = tmp_path / "src"
    src.mkdir()
    _make_template(src, "python")
    result = CliRunner().invoke(app, ["add", str(src), "--name", "x"])
    assert result.exit_code == 1
    assert "--name cannot be used" in result.output


def test_add_ref_for_local_source_is_rejected(
    tmp_path: Path, store: TemplateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(context, "store", store)
    src = _make_template(tmp_path, "python")
    result = CliRunner().invoke(app, ["add", str(src), "--ref", "main"])
    assert result.exit_code == 1
    assert "--ref and --subpath only apply" in result.output
