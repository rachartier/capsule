"""Parses template source strings and fetches them to a local directory."""

import contextlib
import logging
import re
import subprocess
import tempfile
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class RemoteFetchError(Exception):
    """A git source that is malformed or cannot be cloned."""


class GitSubpathNotFound(Exception):
    """A subpath that does not exist in the cloned repository."""


@dataclass(frozen=True)
class LocalSource:
    """A template source on the local filesystem."""

    path: Path


@dataclass(frozen=True)
class GitSource:
    """A template source in a git repository, optionally at a ref and subpath."""

    url: str
    ref: str | None
    subpath: str | None


_GH_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?"
    r"(?:/tree/(?P<ref>[^/]+)(?:/(?P<subpath>.+?))?)?/?$"
)
_SCP_GIT_RE = re.compile(r"^[\w.-]+@[\w.-]+:[\w./~-]+$")


def _parse_gh_shorthand(raw: str) -> GitSource:
    owner, slash, rest = raw.removeprefix("gh:").partition("/")
    if not slash or not owner:
        raise RemoteFetchError(
            f"Invalid gh: shorthand '{raw}'. Expected 'gh:owner/repo[@ref][/subpath]'."
        )

    repo_ref, _, subpath = rest.partition("/")
    repo, _, ref = repo_ref.partition("@")
    if not repo:
        raise RemoteFetchError(f"Invalid gh: shorthand '{raw}'. Repo name is empty.")

    return GitSource(
        url=f"https://github.com/{owner}/{repo}.git",
        ref=ref or None,
        subpath=subpath or None,
    )


def parse_source(raw: str) -> LocalSource | GitSource:
    """Parses a source string given on the command line.

    Args:
        raw: A local path, `gh:owner/repo[@ref][/subpath]`, a GitHub tree URL
            or any git remote URL.

    Returns:
        The git source for anything that looks like a remote, else the local
        path resolved to an absolute one.

    Raises:
        RemoteFetchError: A `gh:` shorthand is malformed.
    """
    if raw.startswith("gh:"):
        return _parse_gh_shorthand(raw)

    if m := _GH_URL_RE.match(raw):
        return GitSource(
            url=f"https://github.com/{m['owner']}/{m['repo']}.git",
            ref=m["ref"],
            subpath=m["subpath"],
        )

    if (
        raw.startswith(("http://", "https://", "ssh://", "git://", "git+"))
        or raw.endswith(".git")
        or _SCP_GIT_RE.match(raw)
    ):
        return GitSource(url=raw, ref=None, subpath=None)

    return LocalSource(path=Path(raw).expanduser().resolve())


@contextlib.contextmanager
def materialize(source: LocalSource | GitSource) -> Generator[Path]:
    """Makes a source available as a local directory for the duration of the block.

    A git source is shallow-cloned into a temporary directory that is removed
    on exit.

    Args:
        source: The source to fetch.

    Yields:
        The local directory holding the source, at its subpath if any.

    Raises:
        RemoteFetchError: git is missing or the clone failed.
        GitSubpathNotFound: The subpath does not exist in the repository.
    """
    if isinstance(source, LocalSource):
        yield source.path
        return

    with tempfile.TemporaryDirectory(prefix="capsule-fetch-") as tmp:
        repo = Path(tmp) / "repo"
        _git_clone(source, repo)

        root = repo / source.subpath if source.subpath else repo
        if not root.is_dir():
            raise GitSubpathNotFound(
                f"Subpath {source.subpath!r} not found in {source.url}"
            )

        yield root


def _git_clone(source: GitSource, dest: Path) -> None:
    cmd = ["git", "clone", "--depth", "1"]
    if source.ref:
        cmd += ["--branch", source.ref]
    # `--` stops git from reading a source that starts with `-` as an option.
    cmd += ["--", source.url, str(dest)]

    log.info("git clone: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise RemoteFetchError(
            "git is required to fetch remote templates but was not found on PATH."
        ) from e
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip().splitlines()
        tail = stderr[-1] if stderr else f"git exited with status {e.returncode}"
        raise RemoteFetchError(f"Failed to clone {source.url}: {tail}") from e
