"""Reads pull requests from the GitHub REST API. Read-only: the gate never writes to GitHub.

`GITHUB_TOKEN` is optional for public repositories and raises the rate limit.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from ownership_gate.model import ChangedFile, CheckRun, PullRequest

API = "https://api.github.com"
TRAILER = re.compile(r"^Entire-Checkpoint:\s*([0-9A-Za-z]+)\s*$", re.MULTILINE)
PAGE_SIZE = 100
# GitHub lists at most 3,000 files and 250 commits per PR, so 30 pages always suffice.
MAX_PAGES = 30

GetJson = Callable[[str], Any]


class GitHubError(RuntimeError):
    pass


def http_get_json(url: str) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ownership-gate"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        hint = " (rate limited; set GITHUB_TOKEN)" if err.code in (403, 429) else ""
        raise GitHubError(f"{url} returned {err.code}{hint}") from err
    except urllib.error.URLError as err:
        raise GitHubError(f"{url} unreachable: {err.reason}") from err


def get_all(url: str, get: GetJson = http_get_json) -> list[Any]:
    """Every item of a paginated list endpoint. `url` already carries `per_page`."""
    items: list[Any] = []
    for page in range(1, MAX_PAGES + 1):
        batch = get(url if page == 1 else f"{url}&page={page}")
        items.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
    return items


def open_pulls(
    repo: str, author: str | None = None, get: GetJson = http_get_json
) -> list[tuple[int, str]]:
    """`(number, head sha)` of each open PR, so callers skip PRs whose head is unchanged."""
    pulls = get_all(f"{API}/repos/{repo}/pulls?state=open&per_page={PAGE_SIZE}", get)
    return [
        (p["number"], p["head"]["sha"])
        for p in pulls
        if author is None or p["user"]["login"].casefold() == author.casefold()
    ]


def fetch_pull_request(repo: str, number: int, get: GetJson = http_get_json) -> PullRequest:
    base = f"{API}/repos/{repo}/pulls/{number}"
    pull = get(base)
    head_sha = pull["head"]["sha"]
    files = get_all(f"{base}/files?per_page={PAGE_SIZE}", get)
    commits = get_all(f"{base}/commits?per_page={PAGE_SIZE}", get)
    runs = get(f"{API}/repos/{repo}/commits/{head_sha}/check-runs?per_page={PAGE_SIZE}")
    return PullRequest(
        repo=repo,
        number=number,
        author=pull["user"]["login"],
        title=pull.get("title") or "",
        body=pull.get("body") or "",
        head_sha=head_sha,
        files=tuple(
            ChangedFile(f["filename"], f.get("additions", 0), f.get("deletions", 0)) for f in files
        ),
        checks=tuple(CheckRun(r["name"], r.get("conclusion")) for r in runs.get("check_runs", [])),
        checkpoint_ids=checkpoint_ids(c["commit"]["message"] for c in commits),
    )


def checkpoint_ids(messages: Any) -> tuple[str, ...]:
    """Entire checkpoint ids from commit message trailers, oldest first, without repeats."""
    seen: dict[str, None] = {}
    for message in messages:
        for found in TRAILER.findall(message or ""):
            seen.setdefault(found, None)
    return tuple(seen)
