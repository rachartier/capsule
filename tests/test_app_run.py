import json
from pathlib import Path

from capsule.app import _read_devcontainer_shell


def _write_devcontainer(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestReadDevcontainerShell:
    def test_reads_shell_from_config_path(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"customizations": {"capsule": {"shell": "/bin/bash"}}})
        assert _read_devcontainer_shell(str(dc), str(tmp_path)) == "/bin/bash"

    def test_reads_shell_from_local_devcontainer(self, tmp_path: Path) -> None:
        dc = tmp_path / ".devcontainer" / "devcontainer.json"
        _write_devcontainer(dc, {"customizations": {"capsule": {"shell": "/bin/zsh"}}})
        assert _read_devcontainer_shell(None, str(tmp_path)) == "/bin/zsh"

    def test_returns_none_when_capsule_customization_absent(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"name": "test"})
        assert _read_devcontainer_shell(str(dc), str(tmp_path)) is None

    def test_returns_none_when_shell_key_absent(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"customizations": {"capsule": {"otherKey": "value"}}})
        assert _read_devcontainer_shell(str(dc), str(tmp_path)) is None

    def test_returns_none_when_file_missing_with_config_path(self, tmp_path: Path) -> None:
        assert _read_devcontainer_shell(str(tmp_path / "nonexistent.json"), str(tmp_path)) is None

    def test_returns_none_when_no_local_devcontainer(self, tmp_path: Path) -> None:
        assert _read_devcontainer_shell(None, str(tmp_path)) is None

    def test_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        dc.write_text("{bad json", encoding="utf-8")
        assert _read_devcontainer_shell(str(dc), str(tmp_path)) is None

    def test_returns_none_when_customizations_not_a_dict(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"customizations": "not-a-dict"})
        assert _read_devcontainer_shell(str(dc), str(tmp_path)) is None
