"""Thin, local-only git helpers for seal and verify. No network commands."""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

TRAILER_KEY = "Flipside-Seal"
_TRAILER = re.compile(r"^v1 root=([0-9a-f]{64}) n=([1-9][0-9]*) manifest=([0-9a-f]{64})$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


class GitError(RuntimeError):
    """A git command failed."""


@dataclass(frozen=True)
class SealTrailer:
    """The parsed ``Flipside-Seal:`` trailer."""

    root: str
    n: int
    manifest: str

    def line(self) -> str:
        return f"v1 root={self.root} n={self.n} manifest={self.manifest}"


def git(repo: Path, *args: str, input_text: str | None = None, check: bool = True) -> str:
    """Run git in ``repo`` and return stdout. Raises GitError when check is set and it fails."""
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        input=input_text,
        check=False,
    )
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def git_ok(repo: Path, *args: str) -> bool:
    """True when the git command exits 0."""
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    return p.returncode == 0


def toplevel(path: Path) -> Path:
    return Path(git(path, "rev-parse", "--show-toplevel").strip())


def common_dir(repo: Path) -> Path:
    d = Path(git(repo, "rev-parse", "--git-common-dir").strip())
    return d if d.is_absolute() else (repo / d).resolve()


def resolve_commit(repo: Path, ref: str) -> str | None:
    """Full SHA of a commit, or None when it does not exist."""
    p = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    sha = p.stdout.strip()
    return sha if p.returncode == 0 and HEX40.match(sha) else None


def changed_files(repo: Path, base: str) -> list[str]:
    """``git diff --name-only <base>...HEAD``, sorted."""
    out = git(repo, "diff", "--name-only", f"{base}...HEAD")
    return sorted(line for line in out.splitlines() if line)


def trailer_values(repo: Path, commit: str) -> list[str]:
    """Every Flipside-Seal trailer value on a commit (``git interpret-trailers --parse``)."""
    msg = git(repo, "show", "-s", "--format=%B", commit)
    parsed = git(repo, "interpret-trailers", "--parse", input_text=msg)
    out = []
    for line in parsed.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip().lower() == TRAILER_KEY.lower():
            out.append(value.strip())
    return out


def parse_trailer(value: str) -> SealTrailer | None:
    m = _TRAILER.match(value)
    return SealTrailer(m.group(1), int(m.group(2)), m.group(3)) if m else None
