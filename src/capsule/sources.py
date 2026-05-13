import contextlib
import logging
import re
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class RemoteFetchError(Exception):
    pass


class GitSubpathNotFound(Exception):
    pass


@dataclass(frozen=True)
class LocalSource:
    path: Path


@dataclass(frozen=True)
class GitSource:
    url: str
    ref: str | None
    subpath: str | None


_GH_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?"
    r"(?:/tree/(?P<ref>[^/]+)(?:/(?P<subpath>.+?))?)?/?$"
)
_SCP_GIT_RE = re.compile(r"^[\w.-]+@[\w.-]+:[\w./~-]+$")


def parse_source(raw: str) -> LocalSource | GitSource:
    if raw.startswith("gh:"):
        owner, slash, rest = raw[3:].partition("/")
        if not slash or not owner:
            raise RemoteFetchError(f"Invalid gh: shorthand '{raw}'. Expected 'gh:owner/repo[@ref][/subpath]'.")
        repo_ref, _, subpath_str = rest.partition("/")
        repo, _, ref_str = repo_ref.partition("@")
        if not repo:
            raise RemoteFetchError(f"Invalid gh: shorthand '{raw}'. Repo name is empty.")
        return GitSource(
            url=f"https://github.com/{owner}/{repo}.git",
            ref=ref_str or None,
            subpath=subpath_str or None,
        )

    if m := _GH_URL_RE.match(raw):
        owner, repo = m.group("owner"), m.group("repo")
        return GitSource(
            url=f"https://github.com/{owner}/{repo}.git",
            ref=m.group("ref"),
            subpath=m.group("subpath"),
        )

    if (
        raw.startswith(("http://", "https://", "ssh://", "git://", "git+"))
        or raw.endswith(".git")
        or _SCP_GIT_RE.match(raw)
    ):
        return GitSource(url=raw, ref=None, subpath=None)

    return LocalSource(path=Path(raw).expanduser().resolve())


@contextlib.contextmanager
def materialize(source: LocalSource | GitSource) -> Iterator[Path]:
    if isinstance(source, LocalSource):
        yield source.path
        return
    with tempfile.TemporaryDirectory(prefix="capsule-fetch-") as tmp:
        tmp_path = Path(tmp) / "repo"
        _git_clone(source, tmp_path)
        root = tmp_path / source.subpath if source.subpath else tmp_path
        if not root.is_dir():
            raise GitSubpathNotFound(
                f"Subpath {source.subpath!r} not found in {source.url}"
            )
        yield root


def _git_clone(source: GitSource, dest: Path) -> None:
    cmd = ["git", "clone", "--depth", "1"]
    if source.ref:
        cmd += ["--branch", source.ref]
    cmd += [source.url, str(dest)]
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
