import json
from pathlib import Path

from capsule.app import _devcontainer_mount_paths, _read_devcontainer_shell


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

    def test_returns_none_when_capsule_customization_absent(
        self, tmp_path: Path
    ) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"name": "test"})
        assert _read_devcontainer_shell(str(dc), str(tmp_path)) is None

    def test_returns_none_when_shell_key_absent(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"customizations": {"capsule": {"otherKey": "value"}}})
        assert _read_devcontainer_shell(str(dc), str(tmp_path)) is None

    def test_returns_none_when_file_missing_with_config_path(
        self, tmp_path: Path
    ) -> None:
        assert (
            _read_devcontainer_shell(str(tmp_path / "nonexistent.json"), str(tmp_path))
            is None
        )

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


class TestDevcontainerMountPaths:
    def test_string_mount_format(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(
            dc, {"mounts": ["type=bind,source=/host/foo,target=/container/foo"]}
        )
        result = _devcontainer_mount_paths(str(dc), str(tmp_path))
        assert "/host/foo" in result
        assert "/container/foo" in result

    def test_object_mount_format(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(
            dc,
            {
                "mounts": [
                    {"type": "bind", "source": "/host/bar", "target": "/container/bar"}
                ]
            },
        )
        result = _devcontainer_mount_paths(str(dc), str(tmp_path))
        assert "/host/bar" in result
        assert "/container/bar" in result

    def test_mixed_mount_formats(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(
            dc,
            {
                "mounts": [
                    "type=bind,source=/host/a,target=/container/a",
                    {"type": "bind", "source": "/host/b", "target": "/container/b"},
                ]
            },
        )
        result = _devcontainer_mount_paths(str(dc), str(tmp_path))
        assert result == {"/host/a", "/container/a", "/host/b", "/container/b"}

    def test_reads_from_local_devcontainer_when_no_config_path(
        self, tmp_path: Path
    ) -> None:
        dc = tmp_path / ".devcontainer" / "devcontainer.json"
        _write_devcontainer(dc, {"mounts": ["source=/s,target=/t"]})
        result = _devcontainer_mount_paths(None, str(tmp_path))
        assert "/s" in result
        assert "/t" in result

    def test_returns_empty_when_no_mounts_key(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"name": "test"})
        assert _devcontainer_mount_paths(str(dc), str(tmp_path)) == set()

    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        assert (
            _devcontainer_mount_paths(str(tmp_path / "nonexistent.json"), str(tmp_path))
            == set()
        )

    def test_returns_empty_on_invalid_json(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        dc.write_text("{bad json", encoding="utf-8")
        assert _devcontainer_mount_paths(str(dc), str(tmp_path)) == set()

    def test_returns_empty_when_no_local_devcontainer(self, tmp_path: Path) -> None:
        assert _devcontainer_mount_paths(None, str(tmp_path)) == set()


class TestBuildExecCmd:
    def test_uid_gid_injected_as_remote_env(self) -> None:
        import os

        from capsule.app import _build_exec_cmd
        from capsule.run_config import RunConfig

        cfg = RunConfig()
        cmd = _build_exec_cmd(None, cfg, "/workspace")
        uid_entry = f"UID={os.getuid()}"
        gid_entry = f"GID={os.getgid()}"
        assert uid_entry in " ".join(cmd)
        assert gid_entry in " ".join(cmd)

    def test_explicit_uid_gid_used(self) -> None:
        from capsule.app import _build_exec_cmd
        from capsule.run_config import RunConfig

        cfg = RunConfig(uid=1234, gid=5678)
        cmd = _build_exec_cmd(None, cfg, "/workspace")
        assert "UID=1234" in " ".join(cmd)
        assert "GID=5678" in " ".join(cmd)
