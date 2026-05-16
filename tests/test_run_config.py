from pathlib import Path

import pytest

from capsule.run_config import RunConfig


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_load_defaults_when_no_file(tmp_path: Path) -> None:
    cfg = RunConfig.load(tmp_path / "nonexistent.toml")
    assert cfg.shell == "/bin/bash"
    assert cfg.mounts == []
    assert cfg.dotfiles == []
    assert cfg.env == {}
    assert cfg.quiet is True


def test_load_shell(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[run]\nshell = "/bin/zsh"\n')
    assert RunConfig.load(p).shell == "/bin/zsh"


def test_load_quiet_false(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, "[run]\nquiet = false\n")
    assert RunConfig.load(p).quiet is False


def test_load_mounts(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[volumes]\nmounts = ["/a:/b", "/c:/d"]\n')
    assert RunConfig.load(p).mounts == ["/a:/b", "/c:/d"]


def test_load_dotfiles(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[dotfiles]\nmounts = ["~/.zshrc:/home/user/.zshrc"]\n')
    assert RunConfig.load(p).dotfiles == ["~/.zshrc:/home/user/.zshrc"]


def test_load_env(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[env]\nMY_VAR = "hello"\n')
    assert RunConfig.load(p).env["MY_VAR"] == "hello"


def test_load_env_expands_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_HOME", "/home/test")
    p = tmp_path / "config.toml"
    _write(p, '[env]\nPATH_VAR = "$MY_HOME/bin"\n')
    assert RunConfig.load(p).env["PATH_VAR"] == "/home/test/bin"


def test_load_env_warns_on_undefined_var(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[env]\nBAD = "$CAPSULE_UNDEFINED_VAR_XYZ/bin"\n')
    import logging
    with caplog.at_level(logging.WARNING, logger="capsule.run_config"):
        RunConfig.load(p)
    assert any("CAPSULE_UNDEFINED_VAR_XYZ" in r.message or "BAD" in r.message for r in caplog.records)


def test_expand_mount_tilde() -> None:
    result = RunConfig.expand_mount("~/.zshrc:/home/user/.zshrc")
    assert not result.startswith("~")
    assert ":" in result


def test_expand_mount_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOTFILES", "/home/user/dotfiles")
    result = RunConfig.expand_mount("$DOTFILES:/dotfiles")
    assert result.startswith("/home/user/dotfiles")


def test_all_mounts_combines(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[volumes]\nmounts = ["/a:/b"]\n[dotfiles]\nmounts = ["/c:/d"]\n')
    cfg = RunConfig.load(p)
    assert cfg.all_mounts() == ["/a:/b", "/c:/d"]


def test_mount_to_devcontainer_format() -> None:
    result = RunConfig.mount_to_devcontainer_format("/host:/container")
    assert result == "type=bind,source=/host,target=/container"
