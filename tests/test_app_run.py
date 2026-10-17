import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import capsule.app as app_module
import capsule.cli.run as run_module
import capsule.containers as containers_module
from capsule.cli import context
from capsule.templates import TemplateStore


def _write_devcontainer(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_ps_without_container_cli_reports_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(containers_module.shutil, "which", lambda _: None)
    result = CliRunner().invoke(app_module.app, ["ps"])
    assert result.exit_code == 1
    assert "docker or podman not found" in result.output


@pytest.fixture
def local_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module, "CONFIG_FILE", tmp_path / "config.toml")
    monkeypatch.setattr(run_module.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    return tmp_path


@pytest.mark.parametrize(
    ("flag", "no_cache"), [("--recreate", False), ("--rebuild", True)]
)
def test_run_recreate_and_rebuild_flags(
    flag: str, no_cache: bool, local_project: Path
) -> None:
    _write_devcontainer(local_project / ".devcontainer" / "devcontainer.json", {})
    result = CliRunner().invoke(app_module.app, ["run", flag, "--dry-run"])
    assert result.exit_code == 0
    output = result.output.replace("\n", " ")
    assert "--remove-existing-container" in output
    assert ("--build-no-cache" in output) is no_cache


def test_run_uses_devcontainer_shell(local_project: Path) -> None:
    _write_devcontainer(
        local_project / ".devcontainer" / "devcontainer.json",
        {"customizations": {"capsule": {"shell": "/bin/zsh"}}},
    )
    result = CliRunner().invoke(app_module.app, ["run", "--dry-run"])
    assert result.exit_code == 0
    assert "-- /bin/zsh" in result.output.replace("\n", " ")


def test_run_reports_invalid_devcontainer_json(local_project: Path) -> None:
    dc = local_project / ".devcontainer" / "devcontainer.json"
    dc.parent.mkdir()
    dc.write_text("{bad json", encoding="utf-8")
    result = CliRunner().invoke(app_module.app, ["run", "--dry-run"])
    assert result.exit_code == 1
    assert "Invalid JSON" in result.output


def test_run_without_devcontainer_or_templates_hints_add(
    local_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(context, "store", TemplateStore(local_project / "templates"))
    result = CliRunner().invoke(app_module.app, ["run", "--dry-run"])
    assert result.exit_code == 1
    assert "Run `capsule add` to store a template first." in result.output


def test_run_applies_override_of_picked_template(
    local_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TemplateStore(local_project / "templates")
    _write_devcontainer(local_project / "py" / "devcontainer.json", {})
    store.add(local_project / "py", "py")
    store.save_run_override("py", uid=4242, gid=None)
    monkeypatch.setattr(context, "store", store)
    result = CliRunner().invoke(app_module.app, ["run", "--dry-run"])
    assert result.exit_code == 0
    assert "UID=4242" in result.output.replace("\n", " ")
