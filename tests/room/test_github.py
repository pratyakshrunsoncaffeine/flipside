"""GitHub PR reader, on canned gh output (synthetic)."""

import json
from collections.abc import Sequence

import pytest

from flipside.room.github import GitHubError, fetch_pr
from flipside.room.rules import CheckRun

SHA = "a" * 40


def fake(args: Sequence[str]) -> str:
    path = next(a for a in args if a.startswith("repos/"))
    if path.endswith("/pulls/142"):
        return json.dumps(
            {
                "number": 142,
                "title": "Add CSV export",
                "body": None,
                "user": {"login": "priya"},
                "head": {"sha": SHA},
            }
        )
    if path.endswith("/pulls/142/files"):
        return "reports/export.py\nauth/session.py\n"
    if path.endswith(f"/commits/{SHA}/check-runs"):
        return '{"name":"tests","conclusion":"success"}\n{"name":"lint","conclusion":null}\n'
    raise AssertionError(path)


def test_fetch_pr_maps_every_field() -> None:
    pr = fetch_pr("acme/app", 142, run=fake)
    assert (pr.number, pr.title, pr.body, pr.author) == (142, "Add CSV export", "", "priya")
    assert pr.files == ("reports/export.py", "auth/session.py")
    assert pr.checks == (CheckRun("tests", "success"), CheckRun("lint", None))


def test_files_are_read_across_pages() -> None:
    calls: list[list[str]] = []

    def spy(args: Sequence[str]) -> str:
        calls.append(list(args))
        return fake(args)

    fetch_pr("acme/app", 142, run=spy)
    files_call = next(c for c in calls if any(a.endswith("/files") for a in c))
    assert "--paginate" in files_call


@pytest.mark.parametrize("slug", ["acme", "acme/app/extra", "acme/app;rm", ""])
def test_bad_slug_is_refused_before_gh_runs(slug: str) -> None:
    with pytest.raises(GitHubError):
        fetch_pr(slug, 142, run=fake)


def test_bad_response_is_an_error() -> None:
    with pytest.raises(GitHubError):
        fetch_pr("acme/app", 142, run=lambda _a: "[]")
