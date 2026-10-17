import json
import os
from pathlib import Path

import pytest

from capsule.devcontainer import (
    Workspace,
    capsule_shell,
    exec_command,
    load_devcontainer,
    mount_paths,
    up_command,
)
from capsule.run_config import RunConfig
from capsule.templates import InvalidJSON


def _write_devcontainer(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestLoadDevcontainer:
    def test_reads_object(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, {"name": "test"})
        assert load_devcontainer(dc) == {"name": "test"}

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        dc.write_text("{bad json", encoding="utf-8")
        with pytest.raises(InvalidJSON):
            load_devcontainer(dc)

    def test_raises_when_not_an_object(self, tmp_path: Path) -> None:
        dc = tmp_path / "devcontainer.json"
        _write_devcontainer(dc, ["not", "an", "object"])
        with pytest.raises(InvalidJSON, match="JSON object"):
            load_devcontainer(dc)

    def test_raises_when_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_devcontainer(tmp_path / "nonexistent.json")


class TestWorkspace:
    def test_uses_template_config(self, tmp_path: Path) -> None:
        dc = tmp_path / "template" / "devcontainer.json"
        assert Workspace(tmp_path, "t", dc).devcontainer_json == dc

    def test_falls_back_to_local_devcontainer(self, tmp_path: Path) -> None:
        assert (
            Workspace(tmp_path).devcontainer_json
            == tmp_path / ".devcontainer" / "devcontainer.json"
        )


class TestCapsuleShell:
    def test_reads_shell(self) -> None:
        dc = {"customizations": {"capsule": {"shell": "/bin/bash"}}}
        assert capsule_shell(dc) == "/bin/bash"

    def test_none_when_capsule_customization_absent(self) -> None:
        assert capsule_shell({"name": "test"}) is None

    def test_none_when_shell_key_absent(self) -> None:
        assert capsule_shell({"customizations": {"capsule": {"otherKey": "v"}}}) is None

    def test_none_when_customizations_not_a_dict(self) -> None:
        assert capsule_shell({"customizations": "not-a-dict"}) is None


class TestMountPaths:
    def test_string_mount_format(self) -> None:
        dc = {"mounts": ["type=bind,source=/host/foo,target=/container/foo"]}
        assert mount_paths(dc) == {"/host/foo", "/container/foo"}

    def test_object_mount_format(self) -> None:
        dc = {"mounts": [{"type": "bind", "source": "/host/bar", "target": "/c/bar"}]}
        assert mount_paths(dc) == {"/host/bar", "/c/bar"}

    def test_mixed_mount_formats(self) -> None:
        dc = {
            "mounts": [
                "type=bind,source=/host/a,target=/container/a",
                {"type": "bind", "source": "/host/b", "target": "/container/b"},
            ]
        }
        assert mount_paths(dc) == {"/host/a", "/container/a", "/host/b", "/container/b"}

    def test_empty_when_no_mounts_key(self) -> None:
        assert mount_paths({"name": "test"}) == set()


class TestExecCommand:
    def test_uid_gid_default_to_host(self) -> None:
        cmd = " ".join(exec_command(Workspace(Path("/workspace")), RunConfig()))
        assert f"UID={os.getuid()}" in cmd
        assert f"GID={os.getgid()}" in cmd

    def test_explicit_uid_gid_used(self) -> None:
        cfg = RunConfig(uid=1234, gid=5678)
        cmd = " ".join(exec_command(Workspace(Path("/workspace")), cfg))
        assert "UID=1234" in cmd
        assert "GID=5678" in cmd

    def test_template_adds_config_and_id_label(self) -> None:
        ws = Workspace(Path("/w"), "t", Path("/store/t/devcontainer.json"))
        cmd = exec_command(ws, RunConfig())
        assert cmd[cmd.index("--config") + 1] == "/store/t/devcontainer.json"
        assert cmd[cmd.index("--id-label") + 1] == "capsule.workspace=/w"


class TestUpCommand:
    def test_skips_mounts_already_declared(self) -> None:
        cfg = RunConfig(mounts=["/a:/b", "/c:/d"])
        cmd = up_command(
            Workspace(Path("/w")), cfg, {"/d"}, rebuild=False, recreate=False
        )
        assert "type=bind,source=/a,target=/b" in cmd
        assert "type=bind,source=/c,target=/d" not in cmd

    @pytest.mark.parametrize(
        ("rebuild", "recreate", "remove", "no_cache"),
        [
            (False, False, False, False),
            (False, True, True, False),
            (True, False, True, True),
        ],
    )
    def test_rebuild_and_recreate_flags(
        self, *, rebuild: bool, recreate: bool, remove: bool, no_cache: bool
    ) -> None:
        cmd = up_command(
            Workspace(Path("/w")),
            RunConfig(),
            set(),
            rebuild=rebuild,
            recreate=recreate,
        )
        assert ("--remove-existing-container" in cmd) is remove
        assert ("--build-no-cache" in cmd) is no_cache
