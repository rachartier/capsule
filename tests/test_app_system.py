from pathlib import Path

import pytest
from typer.testing import CliRunner

from capsule import containers
from capsule.app import app
from capsule.cli import config as config_cmd
from capsule.cli import context, doctor
from capsule.containers import Container, ContainerCliError
from capsule.templates import TemplateStore

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TemplateStore:
    store = TemplateStore(tmp_path / "templates")
    monkeypatch.setattr(context, "store", store)
    return store


@pytest.fixture
def config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "capsule" / "config.toml"
    monkeypatch.setattr(config_cmd, "CONFIG_FILE", path)
    monkeypatch.setattr(doctor, "CONFIG_FILE", path)
    return path


# -- capsule config --


def test_config_without_file_reports_defaults(config_file: Path) -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "Using defaults" in result.output


def test_config_shows_resolved_values(config_file: Path) -> None:
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        '[run]\nshell = "/bin/zsh"\nuid = 42\n[env]\nFOO = "bar"\n[volumes]\nmounts = ["/a:/b"]\n'
    )
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    for text in ("/bin/zsh", "42", "FOO=bar", "/a:/b"):
        assert text in result.output


def test_config_with_invalid_file_exits(config_file: Path) -> None:
    config_file.parent.mkdir(parents=True)
    config_file.write_text("[run\n")
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 1
    assert "Invalid TOML" in result.output


def test_config_init_creates_a_loadable_file(config_file: Path) -> None:
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 0
    assert config_cmd.RunConfig.load(config_file).quiet is False


def test_config_init_refuses_to_overwrite_without_force(config_file: Path) -> None:
    config_file.parent.mkdir(parents=True)
    config_file.write_text("# mine\n")
    result = runner.invoke(app, ["config", "init"])
    assert result.exit_code == 1
    assert config_file.read_text() == "# mine\n"

    result = runner.invoke(app, ["config", "init", "--force"])
    assert result.exit_code == 0
    assert config_file.read_text() != "# mine\n"


# -- capsule doctor --


def _healthy_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "/usr/bin/devcontainer")
    monkeypatch.setattr(containers, "find_container_cli", lambda: "docker")


def test_doctor_passes_when_everything_is_healthy(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _healthy_tools(monkeypatch)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0


def test_doctor_fails_without_tools(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _: None)
    monkeypatch.setattr(containers, "find_container_cli", lambda: None)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "devcontainer CLI not found" in result.output
    assert "No container runtime" in result.output


def test_doctor_fails_on_invalid_template(
    config_file: Path, isolated_store: TemplateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _healthy_tools(monkeypatch)
    template = isolated_store._dir / "broken"
    template.mkdir(parents=True)
    (template / "devcontainer.json").write_text("{not json")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "Template 'broken'" in result.output


def test_doctor_fails_on_template_without_devcontainer_json(
    config_file: Path, isolated_store: TemplateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    _healthy_tools(monkeypatch)
    (isolated_store._dir / "empty").mkdir(parents=True)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "missing devcontainer.json" in result.output


def test_doctor_fails_on_invalid_config(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _healthy_tools(monkeypatch)
    config_file.parent.mkdir(parents=True)
    config_file.write_text('[volumes]\nmounts = ["/a:/b:ro"]\n')
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "config.toml is invalid" in result.output


# -- capsule ps / stop --


def _fake_cli(monkeypatch: pytest.MonkeyPatch, found: list[Container]) -> list[str]:
    actions: list[str] = []
    monkeypatch.setattr(containers, "find_container_cli", lambda: "docker")
    monkeypatch.setattr(containers, "list_devcontainers", lambda cli: found)
    monkeypatch.setattr(
        containers, "stop", lambda cli, c: actions.append(f"stop {c.id}")
    )
    monkeypatch.setattr(
        containers, "remove", lambda cli, c: actions.append(f"rm {c.id}")
    )
    return actions


def test_ps_requires_a_container_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(containers, "find_container_cli", lambda: None)
    result = runner.invoke(app, ["ps"])
    assert result.exit_code == 1
    assert "docker or podman not found" in result.output


def test_ps_with_no_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_cli(monkeypatch, [])
    result = runner.invoke(app, ["ps"])
    assert result.exit_code == 0
    assert "No devcontainers" in result.output


def test_ps_lists_containers(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_cli(monkeypatch, [Container("a", "web", "/proj/a", "Up 2m")])
    result = runner.invoke(app, ["ps"])
    assert result.exit_code == 0
    assert "web" in result.output
    assert "/proj/a" in result.output


def test_ps_reports_container_cli_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(containers, "find_container_cli", lambda: "docker")

    def fail(cli: str) -> list[Container]:
        raise ContainerCliError("docker is down")

    monkeypatch.setattr(containers, "list_devcontainers", fail)
    result = runner.invoke(app, ["ps"])
    assert result.exit_code == 1
    assert "docker is down" in result.output


def test_stop_stops_the_running_container_of_a_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions = _fake_cli(
        monkeypatch,
        [
            Container("a", "web", str(tmp_path), "Up 2m"),
            Container("b", "other", "/elsewhere", "Up 2m"),
        ],
    )
    result = runner.invoke(app, ["stop", str(tmp_path)])
    assert result.exit_code == 0
    assert actions == ["stop a"]


def test_stop_skips_an_already_stopped_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions = _fake_cli(
        monkeypatch, [Container("a", "web", str(tmp_path), "Exited (0)")]
    )
    result = runner.invoke(app, ["stop", str(tmp_path)])
    assert result.exit_code == 0
    assert "already stopped" in result.output
    assert actions == []


def test_stop_force_removes_even_a_stopped_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    actions = _fake_cli(
        monkeypatch, [Container("a", "web", str(tmp_path), "Exited (0)")]
    )
    result = runner.invoke(app, ["stop", "--force", str(tmp_path)])
    assert result.exit_code == 0
    assert actions == ["rm a"]


def test_stop_without_a_matching_container_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_cli(monkeypatch, [Container("a", "web", "/elsewhere", "Up 2m")])
    result = runner.invoke(app, ["stop", str(tmp_path)])
    assert result.exit_code == 1
    assert "No devcontainer found" in result.output
