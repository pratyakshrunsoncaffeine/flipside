import subprocess
from pathlib import Path

from ownership_gate.entire import load_session
from ownership_gate.github import PAGE_SIZE, checkpoint_ids, fetch_pull_request, get_all, open_pulls
from ownership_gate.transcript import StepKind
from tests.session_builder import SessionBuilder

RESPONSES = {
    "https://api.github.com/repos/acme/shop/pulls?state=open&per_page=100": [
        {"number": 7, "user": {"login": "Dana"}, "head": {"sha": "abc123"}},
        {"number": 8, "user": {"login": "sam"}, "head": {"sha": "def456"}},
    ],
    "https://api.github.com/repos/acme/shop/pulls/7": {
        "user": {"login": "dana"},
        "title": "Refunds",
        "body": None,
        "head": {"sha": "abc123"},
    },
    "https://api.github.com/repos/acme/shop/pulls/7/files?per_page=100": [
        {"filename": "app/billing.py", "additions": 4, "deletions": 1},
    ],
    "https://api.github.com/repos/acme/shop/pulls/7/commits?per_page=100": [
        {"commit": {"message": "feat: refunds\n\nEntire-Checkpoint: a1b2c3d4e5f6"}},
        {"commit": {"message": "fix\n\nEntire-Checkpoint: a1b2c3d4e5f6"}},
        {"commit": {"message": "docs"}},
    ],
    "https://api.github.com/repos/acme/shop/commits/abc123/check-runs?per_page=100": {
        "check_runs": [{"name": "ci", "conclusion": None}],
    },
}


def test_fetches_a_pull_request_with_trailers_and_checks():
    pr = fetch_pull_request("acme/shop", 7, get=RESPONSES.__getitem__)

    assert (pr.author, pr.body, pr.head_sha) == ("dana", "", "abc123")
    assert pr.files[0].path == "app/billing.py"
    assert pr.checks[0].conclusion is None
    assert pr.checkpoint_ids == ("a1b2c3d4e5f6",)


def test_lists_open_pulls_by_author_case_insensitively():
    assert open_pulls("acme/shop", "dana", get=RESPONSES.__getitem__) == [(7, "abc123")]


def test_reads_every_page_of_a_list():
    pages = {
        "u?per_page=100": list(range(PAGE_SIZE)),
        "u?per_page=100&page=2": [PAGE_SIZE],
    }

    assert len(get_all("u?per_page=100", pages.__getitem__)) == PAGE_SIZE + 1


def test_trailer_must_be_its_own_line():
    assert checkpoint_ids(["mentions Entire-Checkpoint: abc inline"]) == ()


def _git(repo: Path, *args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], input=stdin, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_loads_and_joins_sessions_from_the_checkpoint_branch(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    first = SessionBuilder().prompt("refunds").bash("pytest", ok=False).lines()
    second = SessionBuilder().prompt("fix it").bash("pytest").text()
    files = {
        "0/full.jsonl": "\n".join(first[:2]) + "\n",
        "0/full.jsonl.001": "\n".join(first[2:]) + "\n",
        "1/full.jsonl": second,
    }
    for name, text in files.items():
        path = repo / "a1" / "b2c3d4e5f6" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
    _git(repo, "checkout", "-q", "--orphan", "entire/checkpoints/v1")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "checkpoint")

    session = load_session(repo, ["a1b2c3d4e5f6"])

    assert session is not None
    assert [s.index for s in session.steps] == [1, 2, 3, 4]
    assert session.steps[1].ok is False, "the result in chunk .001 must join its tool call"
    assert [s.kind for s in session.steps][2] is StepKind.PROMPT
    assert session.steps[3].ok is True


def test_missing_checkpoint_gives_no_session(tmp_path):
    _git(tmp_path, "init", "-q")

    assert load_session(tmp_path, ["ffffffffffff"]) is None
