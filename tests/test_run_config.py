import logging
from pathlib import Path

import pytest

from capsule.run_config import InvalidConfig, RunConfig


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_load_defaults_when_no_file(tmp_path: Path) -> None:
    cfg = RunConfig.load(tmp_path / "nonexistent.toml")
    assert cfg.shell is None
    assert cfg.mounts == []
    assert cfg.env == {}
    assert cfg.quiet is False


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


def test_load_merges_deprecated_dotfiles(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[volumes]\nmounts = ["/a:/b"]\n[dotfiles]\nmounts = ["/c:/d"]\n')
    with caplog.at_level(logging.WARNING, logger="capsule.run_config"):
        cfg = RunConfig.load(p)
    assert cfg.mounts == ["/a:/b", "/c:/d"]
    assert any("deprecated" in r.message for r in caplog.records)


def test_load_empty_dotfiles_does_not_warn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    p = tmp_path / "config.toml"
    _write(p, "[dotfiles]\nmounts = []\n")
    with caplog.at_level(logging.WARNING, logger="capsule.run_config"):
        RunConfig.load(p)
    assert not caplog.records


def test_load_rejects_mount_options(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[volumes]\nmounts = ["~/.ssh:/root/.ssh:ro"]\n')
    with pytest.raises(InvalidConfig, match="read-only"):
        RunConfig.load(p)


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
    with caplog.at_level(logging.WARNING, logger="capsule.run_config"):
        RunConfig.load(p)
    assert any("CAPSULE_UNDEFINED_VAR_XYZ" in r.message for r in caplog.records)


def test_expand_mount_tilde() -> None:
    result = RunConfig.expand_mount("~/.zshrc:/home/user/.zshrc")
    assert not result.startswith("~")
    assert ":" in result


def test_expand_mount_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOTFILES", "/home/user/dotfiles")
    result = RunConfig.expand_mount("$DOTFILES:/dotfiles")
    assert result.startswith("/home/user/dotfiles")


def test_mount_to_devcontainer_format() -> None:
    result = RunConfig.mount_to_devcontainer_format("/host:/container")
    assert result == "type=bind,source=/host,target=/container"


def test_uid_gid_defaults_to_host(tmp_path: Path) -> None:
    import os

    cfg = RunConfig.load(tmp_path / "nonexistent.toml")
    assert cfg.uid is None
    assert cfg.gid is None
    assert cfg.resolved_uid() == os.getuid()
    assert cfg.resolved_gid() == os.getgid()


def test_uid_gid_explicit_values(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, "[run]\nuid = 1234\ngid = 5678\n")
    cfg = RunConfig.load(p)
    assert cfg.uid == 1234
    assert cfg.gid == 5678
    assert cfg.resolved_uid() == 1234
    assert cfg.resolved_gid() == 5678


def test_uid_gid_partial(tmp_path: Path) -> None:
    import os

    p = tmp_path / "config.toml"
    _write(p, "[run]\nuid = 42\n")
    cfg = RunConfig.load(p)
    assert cfg.uid == 42
    assert cfg.gid is None
    assert cfg.resolved_gid() == os.getgid()


@pytest.mark.parametrize("value", ['"abc"', "true", "1.5"])
def test_invalid_uid_rejected(tmp_path: Path, value: str) -> None:
    p = tmp_path / "config.toml"
    _write(p, f"[run]\nuid = {value}\n")
    with pytest.raises(InvalidConfig, match="uid"):
        RunConfig.load(p)


def test_numeric_string_uid_accepted(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, '[run]\ngid = "1000"\n')
    assert RunConfig.load(p).gid == 1000


def test_invalid_toml_raises_invalid_config(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, "[run\n")
    with pytest.raises(InvalidConfig, match="Invalid TOML"):
        RunConfig.load(p)


@pytest.mark.parametrize(
    ("content", "match"),
    [
        ('volumes = "x"\n', r"\[volumes\]"),
        ("env = []\n", r"\[env\]"),
        ("[volumes]\nmounts = [1]\n", "mounts"),
        ('[volumes]\nmounts = "/a:/b"\n', "mounts"),
        ('[dotfiles]\nmounts = "/a:/b"\n', r"\[dotfiles\]"),
        ("[run]\nshell = 3\n", "shell"),
    ],
)
def test_wrongly_typed_values_raise_invalid_config(
    tmp_path: Path, content: str, match: str
) -> None:
    p = tmp_path / "config.toml"
    _write(p, content)
    with pytest.raises(InvalidConfig, match=match):
        RunConfig.load(p)


def test_load_env_writes_booleans_as_lowercase(tmp_path: Path) -> None:
    p = tmp_path / "config.toml"
    _write(p, "[env]\nDEBUG = true\n")
    assert RunConfig.load(p).env == {"DEBUG": "true"}


def test_mount_with_env_var_holding_colon_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CAPSULE_TEST_SRC", "/a:b")
    p = tmp_path / "config.toml"
    _write(p, '[volumes]\nmounts = ["$CAPSULE_TEST_SRC:/x"]\n')
    with pytest.raises(InvalidConfig, match="Invalid mount"):
        RunConfig.load(p)
