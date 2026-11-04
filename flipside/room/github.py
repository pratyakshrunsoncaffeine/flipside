"""Read one pull request's public data from GitHub with the ``gh`` CLI (docs/BUILD.md 7.1).

Title, body, author login, every changed file (all pages), and the check runs on the PR's
head commit. Flipside seals on an empty commit at the head of the PR, so the head commit's
check runs are the seal commit's. Needs ``gh`` logged in; no token is read or stored here.
"""

import json
import re
import subprocess
from collections.abc import Callable, Sequence

from flipside.room.rules import CheckRun, PRData

Runner = Callable[[Sequence[str]], str]
_SLUG = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubError(RuntimeError):
    """``gh`` failed or returned data of the wrong shape."""


def gh(args: Sequence[str]) -> str:
    """Run ``gh`` and return its standard output."""
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60, check=False)
    except FileNotFoundError as e:
        raise GitHubError("the gh CLI is not installed") from e
    if r.returncode != 0:
        raise GitHubError(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def _lines(out: str) -> list[str]:
    return [x for x in out.splitlines() if x.strip()]


def fetch_pr(slug: str, number: int, run: Runner = gh) -> PRData:
    """PR ``number`` of repository ``slug`` (``owner/name``) as ``PRData``."""
    if not _SLUG.match(slug):
        raise GitHubError(f"not an owner/name repository: {slug!r}")
    if number <= 0:
        raise GitHubError(f"not a PR number: {number}")
    pr = json.loads(run(["api", f"repos/{slug}/pulls/{number}"]))
    if not isinstance(pr, dict) or "head" not in pr:
        raise GitHubError(f"unexpected PR response for {slug}#{number}")
    files = _lines(
        run(["api", "--paginate", f"repos/{slug}/pulls/{number}/files", "--jq", ".[].filename"])
    )
    sha = pr["head"]["sha"]
    checks = [
        json.loads(x)
        for x in _lines(
            run(
                [
                    "api",
                    "--paginate",
                    f"repos/{slug}/commits/{sha}/check-runs",
                    "--jq",
                    ".check_runs[] | {name, conclusion}",
                ]
            )
        )
    ]
    return PRData(
        number=int(pr["number"]),
        title=str(pr.get("title") or ""),
        body=str(pr.get("body") or ""),
        author=str((pr.get("user") or {}).get("login") or ""),
        files=tuple(files),
        checks=tuple(CheckRun(str(c["name"]), c.get("conclusion")) for c in checks),
    )


def head_sha(slug: str, number: int, run: Runner = gh) -> str:
    """The PR's head commit, which the reviewer's clone fetches as ``pull/<n>/head``."""
    pr = json.loads(run(["api", f"repos/{slug}/pulls/{number}"]))
    return str(pr["head"]["sha"])
