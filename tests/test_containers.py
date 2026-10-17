import json
import subprocess

import pytest

from capsule import containers
from capsule.containers import list_devcontainers, parse_containers


def test_parse_containers_reads_workspace_label() -> None:
    output = json.dumps(
        {
            "ID": "b",
            "Names": "/web",
            "Labels": "x=y,capsule.workspace=/proj/b",
            "Status": "Up 2m",
        }
    )
    [container] = parse_containers(output)
    assert container.id == "b"
    assert container.name == "web"
    assert container.workspace == "/proj/b"
    assert container.running


def test_parse_containers_skips_unparsable_lines() -> None:
    output = 'not json\n\n{"ID": "a", "Status": "Exited (0)"}'
    [container] = parse_containers(output)
    assert container.id == "a"
    assert container.workspace == ""
    assert not container.running


def test_list_devcontainers_finds_local_and_template_containers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = {"ID": "a", "Labels": "devcontainer.local_folder=/proj/a"}
    template = {"ID": "b", "Labels": "capsule.workspace=/proj/b,x=y"}
    by_label = {
        "label=devcontainer.local_folder": [local, template],
        "label=capsule.workspace": [template],
    }

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        out = "\n".join(json.dumps(c) for c in by_label[cmd[-1]])
        return subprocess.CompletedProcess(cmd, 0, stdout=out)

    monkeypatch.setattr(containers.subprocess, "run", fake_run)
    found = list_devcontainers("docker")
    assert sorted(c.workspace for c in found) == ["/proj/a", "/proj/b"]
