import logging
import re
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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
        return _parse_gh_shorthand(raw[3:])

    if _looks_like_git_url(raw):
        gh = _try_parse_github_url(raw)
        if gh is not None:
            return gh
        return GitSource(url=raw, ref=None, subpath=None)

    return LocalSource(path=Path(raw).expanduser().resolve())


def _parse_gh_shorthand(rest: str) -> GitSource:
    if not rest:
        raise RemoteFetchError("gh: shorthand requires 'owner/repo[@ref][/subpath]'")

    parts = rest.split("/", 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise RemoteFetchError(
            f"Invalid gh: shorthand 'gh:{rest}'. Expected 'gh:owner/repo[@ref][/subpath]'."
        )

    owner = parts[0]
    repo_part = parts[1]
    subpath = parts[2] if len(parts) == 3 and parts[2] else None

    if "@" in repo_part:
        repo, ref = repo_part.split("@", 1)
        ref = ref or None
    else:
        repo, ref = repo_part, None

    if not repo:
        raise RemoteFetchError(
            f"Invalid gh: shorthand 'gh:{rest}'. Repo name is empty."
        )

    return GitSource(
        url=f"https://github.com/{owner}/{repo}.git", ref=ref, subpath=subpath
    )


def _try_parse_github_url(raw: str) -> GitSource | None:
    m = _GH_URL_RE.match(raw)
    if not m:
        return None
    owner = m.group("owner")
    repo = m.group("repo")
    return GitSource(
        url=f"https://github.com/{owner}/{repo}.git",
        ref=m.group("ref"),
        subpath=m.group("subpath"),
    )


def _looks_like_git_url(raw: str) -> bool:
    if raw.startswith(("http://", "https://", "ssh://", "git://", "git+")):
        return True
    if raw.endswith(".git"):
        return True
    if _SCP_GIT_RE.match(raw):
        return True
    return False


def repo_name(url: str) -> str:
    last = url.rstrip("/").rsplit("/", 1)[-1]
    if last.endswith(".git"):
        last = last[:-4]
    return last


@contextmanager
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
