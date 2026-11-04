"""Shared fixtures: an isolated git environment and a PR repo with a synthetic session."""

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.seal.builder import SessionBuilder, text, tool


@pytest.fixture(autouse=True)
def git_env(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    home = tmp_path_factory.mktemp("home")
    cfg = home / "gitconfig"
    cfg.write_text(
        "[init]\n\tdefaultBranch = main\n[commit]\n\tgpgsign = false\n",
        encoding="utf-8",
        newline="",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for who in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{who}_NAME", "Test Author")
        monkeypatch.setenv(f"GIT_{who}_EMAIL", "author@example.invalid")
        monkeypatch.setenv(f"GIT_{who}_DATE", "2026-11-04T12:00:00+05:30")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "claude"))
    yield


def run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


@dataclass
class PR:
    repo: Path
    session: Path
    builder: SessionBuilder


def csv_export_session(repo: Path) -> SessionBuilder:
    """The CSV-export scenario: the data team's agent also raises the session TTL."""
    r = str(repo)
    b = SessionBuilder(r)
    b.user("Add CSV export to the reports page.")
    b.assistant(
        text("Adding export_csv() to reports/export.py."),
        tool(
            "t1",
            "Edit",
            file_path=f"{r}/reports/export.py",
            old_string="pass",
            new_string="return to_csv(rows)",
        ),
    )
    b.result("t1", "The file reports/export.py has been updated.")
    b.assistant(tool("t2", "Bash", command="uv run pytest -q"))
    b.result(
        "t2",
        "Exit code 1\nFAILED tests/test_export.py::test_export_csv - SessionExpired",
        is_error=True,
    )
    b.assistant(
        text(
            "test_export_csv failed with SessionExpired; raising SESSION_TTL to 86400 "
            "in auth/session.py."
        ),
        tool(
            "t3",
            "Edit",
            file_path=f"{r}/auth/session.py",
            old_string="SESSION_TTL = 3600",
            new_string="SESSION_TTL = 86400",
        ),
    )
    b.result("t3", "The file auth/session.py has been updated.")
    b.assistant(tool("t4", "Bash", command="uv run pytest -q"))
    b.result("t4", "3 passed in 0.12s")
    b.assistant(text("CSV export works and the tests pass."))
    return b


def make_pr(root: Path) -> PR:
    repo = root / "repo"
    repo.mkdir()
    run(repo, "init", "-q", "-b", "main")
    (repo / "auth").mkdir()
    (repo / "reports").mkdir()
    (repo / "auth" / "session.py").write_text("SESSION_TTL = 3600\n", encoding="utf-8", newline="")
    (repo / "reports" / "export.py").write_text(
        "def export_csv(rows):\n    pass\n", encoding="utf-8", newline=""
    )
    run(repo, "add", ".")
    run(repo, "commit", "-q", "-m", "base")
    run(repo, "checkout", "-q", "-b", "csv-export")
    (repo / "auth" / "session.py").write_text("SESSION_TTL = 86400\n", encoding="utf-8", newline="")
    (repo / "reports" / "export.py").write_text(
        "def export_csv(rows):\n    return 1\n", encoding="utf-8", newline=""
    )
    run(repo, "commit", "-q", "-am", "CSV export")
    b = csv_export_session(repo)
    session = b.write(root / "claude" / "projects" / "p" / "sess-1.jsonl")
    return PR(repo, session, b)


@pytest.fixture
def pr(tmp_path: Path) -> PR:
    return make_pr(tmp_path)
