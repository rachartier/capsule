import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from capsule.sources import (
    GitSource,
    GitSubpathNotFound,
    LocalSource,
    RemoteFetchError,
    materialize,
    parse_source,
    repo_name,
)


def test_gh_basic():
    s = parse_source("gh:owner/repo")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref=None, subpath=None
    )


def test_gh_with_ref():
    s = parse_source("gh:owner/repo@main")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref="main", subpath=None
    )


def test_gh_with_subpath():
    s = parse_source("gh:owner/repo/templates/python")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref=None, subpath="templates/python"
    )


def test_gh_with_ref_and_subpath():
    s = parse_source("gh:owner/repo@dev/templates/node")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref="dev", subpath="templates/node"
    )


def test_gh_bare_raises():
    with pytest.raises(RemoteFetchError):
        parse_source("gh:")


def test_gh_missing_repo_raises():
    with pytest.raises(RemoteFetchError):
        parse_source("gh:owner")


def test_gh_empty_owner_raises():
    with pytest.raises(RemoteFetchError):
        parse_source("gh:/repo")


def test_github_https_bare():
    s = parse_source("https://github.com/owner/repo")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref=None, subpath=None
    )


def test_github_https_dotgit():
    s = parse_source("https://github.com/owner/repo.git")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref=None, subpath=None
    )


def test_github_https_tree_ref():
    s = parse_source("https://github.com/owner/repo/tree/main")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref="main", subpath=None
    )


def test_github_https_tree_ref_subpath():
    s = parse_source("https://github.com/owner/repo/tree/main/templates/node")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref="main", subpath="templates/node"
    )


def test_github_https_trailing_slash():
    s = parse_source("https://github.com/owner/repo/")
    assert s == GitSource(
        url="https://github.com/owner/repo.git", ref=None, subpath=None
    )


def test_generic_https_dotgit():
    url = "https://mygitlab.com/team/devcontainers.git"
    s = parse_source(url)
    assert s == GitSource(url=url, ref=None, subpath=None)


def test_generic_ssh_protocol():
    url = "ssh://git@mygitlab.com/team/repo.git"
    s = parse_source(url)
    assert s == GitSource(url=url, ref=None, subpath=None)


def test_generic_git_protocol():
    url = "git://example.com/repo.git"
    s = parse_source(url)
    assert s == GitSource(url=url, ref=None, subpath=None)


def test_scp_form():
    url = "git@github.com:owner/repo.git"
    s = parse_source(url)
    assert s == GitSource(url=url, ref=None, subpath=None)


def test_local_relative():
    s = parse_source("templates/python")
    assert isinstance(s, LocalSource)
    assert s.path.is_absolute()
    assert s.path.name == "python"


def test_local_home_expansion():
    s = parse_source("~/projects/myapp")
    assert isinstance(s, LocalSource)
    assert not str(s.path).startswith("~")


def test_local_absolute(tmp_path: Path):
    s = parse_source(str(tmp_path))
    assert s == LocalSource(path=tmp_path)


def test_repo_name_dotgit():
    assert repo_name("https://github.com/owner/myrepo.git") == "myrepo"


def test_repo_name_no_dotgit():
    assert repo_name("https://github.com/owner/myrepo") == "myrepo"


def test_repo_name_trailing_slash():
    assert repo_name("https://github.com/owner/myrepo/") == "myrepo"


def test_materialize_local(tmp_path: Path):
    with materialize(LocalSource(path=tmp_path)) as p:
        assert p == tmp_path


def test_materialize_git_no_subpath():
    source = GitSource(url="https://github.com/owner/repo.git", ref=None, subpath=None)

    def _side_effect(cmd, **kwargs):
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)
        return MagicMock(returncode=0)

    with patch("capsule.sources.subprocess.run", side_effect=_side_effect):
        with materialize(source) as p:
            assert p.is_dir()
            assert p.name == "repo"


def test_materialize_git_with_subpath():
    source = GitSource(
        url="https://github.com/owner/repo.git", ref=None, subpath="templates/python"
    )

    def _side_effect(cmd, **kwargs):
        dest = Path(cmd[-1])
        (dest / "templates" / "python").mkdir(parents=True, exist_ok=True)
        return MagicMock(returncode=0)

    with patch("capsule.sources.subprocess.run", side_effect=_side_effect):
        with materialize(source) as p:
            assert p.is_dir()
            assert p.name == "python"


def test_materialize_git_subpath_missing():
    source = GitSource(
        url="https://github.com/owner/repo.git", ref=None, subpath="does/not/exist"
    )

    def _side_effect(cmd, **kwargs):
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)
        return MagicMock(returncode=0)

    with patch("capsule.sources.subprocess.run", side_effect=_side_effect):
        with pytest.raises(GitSubpathNotFound, match="does/not/exist"):
            with materialize(source):
                pass


def test_materialize_git_not_found_on_path():
    source = GitSource(url="https://github.com/owner/repo.git", ref=None, subpath=None)
    with patch("capsule.sources.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(RemoteFetchError, match="git is required"):
            with materialize(source):
                pass


def test_materialize_git_clone_failure():
    source = GitSource(url="https://github.com/owner/repo.git", ref=None, subpath=None)
    err = subprocess.CalledProcessError(
        128, ["git", "clone"], stderr="fatal: repo not found\n"
    )
    with patch("capsule.sources.subprocess.run", side_effect=err):
        with pytest.raises(RemoteFetchError, match="repo not found"):
            with materialize(source):
                pass


def test_materialize_git_clone_uses_branch_flag():
    source = GitSource(
        url="https://github.com/owner/repo.git", ref="stable", subpath=None
    )

    captured_cmd: list[str] = []

    def _side_effect(cmd, **kwargs):
        captured_cmd.extend(cmd)
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)
        return MagicMock(returncode=0)

    with patch("capsule.sources.subprocess.run", side_effect=_side_effect):
        with materialize(source):
            pass

    assert "--branch" in captured_cmd
    assert "stable" in captured_cmd


def test_materialize_git_clone_depth_1():
    source = GitSource(url="https://github.com/owner/repo.git", ref=None, subpath=None)

    captured_cmd: list[str] = []

    def _side_effect(cmd, **kwargs):
        captured_cmd.extend(cmd)
        dest = Path(cmd[-1])
        dest.mkdir(parents=True, exist_ok=True)
        return MagicMock(returncode=0)

    with patch("capsule.sources.subprocess.run", side_effect=_side_effect):
        with materialize(source):
            pass

    assert "--depth" in captured_cmd
    assert "1" in captured_cmd
