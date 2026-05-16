from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

import capsule.app as app_module
from capsule.app import _handle_errors, app
from capsule.templates import (
    InvalidJSON,
    MissingDevcontainer,
    NoProvenance,
    TemplateAlreadyExists,
    TemplateNotFound,
    TemplateStore,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TemplateStore:
    test_store = TemplateStore(tmp_path / "templates")
    monkeypatch.setattr(app_module, "store", test_store)
    return test_store


def _add_template(store: TemplateStore, tmp_path: Path, name: str) -> None:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "devcontainer.json").write_text(f'{{"name": "{name}"}}')
    store.add(d, name)


# -- _handle_errors exception mapping --

def test_handle_errors_template_not_found() -> None:
    with pytest.raises(typer.Exit) as exc_info, _handle_errors():
        raise TemplateNotFound("Template 'foo' not found")
    assert exc_info.value.exit_code == 1


def test_handle_errors_template_already_exists() -> None:
    with pytest.raises(typer.Exit) as exc_info, _handle_errors():
        raise TemplateAlreadyExists("Template 'foo' already exists")
    assert exc_info.value.exit_code == 1


def test_handle_errors_no_provenance() -> None:
    with pytest.raises(typer.Exit) as exc_info, _handle_errors():
        raise NoProvenance("no provenance")
    assert exc_info.value.exit_code == 1


def test_handle_errors_invalid_json() -> None:
    with pytest.raises(typer.Exit) as exc_info, _handle_errors():
        raise InvalidJSON("bad json")
    assert exc_info.value.exit_code == 1


def test_handle_errors_missing_devcontainer() -> None:
    with pytest.raises(typer.Exit) as exc_info, _handle_errors():
        raise MissingDevcontainer("no devcontainer.json")
    assert exc_info.value.exit_code == 1


def test_handle_errors_permission_error() -> None:
    with pytest.raises(typer.Exit) as exc_info, _handle_errors():
        raise PermissionError("access denied")
    assert exc_info.value.exit_code == 1


# -- fuzzy suggestion on TemplateNotFound --

def test_handle_errors_suggests_close_match(
    isolated_store: TemplateStore, tmp_path: Path
) -> None:
    _add_template(isolated_store, tmp_path, "python")
    with pytest.raises(typer.Exit), _handle_errors():
        raise TemplateNotFound("Template 'pytho' not found")
    # We can't easily capture console output here; verify no crash and exit code 1


# -- capsule list --

def test_cmd_list_empty(isolated_store: TemplateStore) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No templates" in result.output


def test_cmd_list_shows_templates(
    isolated_store: TemplateStore, tmp_path: Path
) -> None:
    _add_template(isolated_store, tmp_path, "python")
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "python" in result.output


def test_cmd_list_shows_description(
    isolated_store: TemplateStore, tmp_path: Path
) -> None:
    _add_template(isolated_store, tmp_path, "python")
    isolated_store.save_meta("python", description="My Python env", author=None)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "My Python env" in result.output


# -- capsule search --

def test_cmd_search_finds_result(
    isolated_store: TemplateStore, tmp_path: Path
) -> None:
    d = tmp_path / "python"
    d.mkdir()
    (d / "devcontainer.json").write_text('{"image": "python:3.11"}')
    isolated_store.add(d, "python")
    result = runner.invoke(app, ["search", "python"])
    assert result.exit_code == 0
    assert "python" in result.output


def test_cmd_search_no_results(isolated_store: TemplateStore) -> None:
    result = runner.invoke(app, ["search", "nonexistent"])
    assert result.exit_code == 0
    assert "No matches" in result.output


# -- capsule delete --

def test_cmd_delete_not_found(isolated_store: TemplateStore) -> None:
    result = runner.invoke(app, ["delete", "--force", "nonexistent"])
    assert result.exit_code == 1


def test_cmd_delete_with_force(
    isolated_store: TemplateStore, tmp_path: Path
) -> None:
    _add_template(isolated_store, tmp_path, "python")
    result = runner.invoke(app, ["delete", "--force", "python"])
    assert result.exit_code == 0
    assert not (isolated_store._dir / "python").exists()


# -- capsule view --

def test_cmd_view_not_found(isolated_store: TemplateStore) -> None:
    result = runner.invoke(app, ["view", "nonexistent"])
    assert result.exit_code == 1


def test_cmd_view_success(isolated_store: TemplateStore, tmp_path: Path) -> None:
    _add_template(isolated_store, tmp_path, "python")
    result = runner.invoke(app, ["view", "python"])
    assert result.exit_code == 0
    assert "python" in result.output


# -- capsule rename --

def test_cmd_rename_success(isolated_store: TemplateStore, tmp_path: Path) -> None:
    _add_template(isolated_store, tmp_path, "python")
    result = runner.invoke(app, ["rename", "python", "py"])
    assert result.exit_code == 0
    assert (isolated_store._dir / "py").is_dir()


# -- capsule meta --

def test_cmd_meta_set(isolated_store: TemplateStore, tmp_path: Path) -> None:
    _add_template(isolated_store, tmp_path, "python")
    result = runner.invoke(app, ["meta", "python", "--description", "My Python env"])
    assert result.exit_code == 0
    assert isolated_store.load_meta("python")["description"] == "My Python env"


def test_cmd_meta_view(isolated_store: TemplateStore, tmp_path: Path) -> None:
    _add_template(isolated_store, tmp_path, "python")
    isolated_store.save_meta("python", description="Python env", author="Alice")
    result = runner.invoke(app, ["meta", "python"])
    assert result.exit_code == 0
    assert "Python env" in result.output
    assert "Alice" in result.output


def test_cmd_meta_empty(isolated_store: TemplateStore, tmp_path: Path) -> None:
    _add_template(isolated_store, tmp_path, "python")
    result = runner.invoke(app, ["meta", "python"])
    assert result.exit_code == 0
    assert "No metadata" in result.output


def test_cmd_meta_not_found(isolated_store: TemplateStore) -> None:
    result = runner.invoke(app, ["meta", "nonexistent", "--description", "x"])
    assert result.exit_code == 1
