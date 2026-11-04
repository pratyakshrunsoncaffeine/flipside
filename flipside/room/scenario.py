"""Fixture cases: a synthetic PR with a sealed agent session, materialised as two repos.

The author's repo is sealed with the demo key and a fixed git clock (synthetic data
only), so a replay gives the same root and commits on every machine. The reviewer's
repo is a clone, as if the author had pushed.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flipside.room.rules import CheckRun, PRData
from flipside.seal.seal import seal

DEMO_KEY = bytes(32)
GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "Demo Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Demo Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
    "GIT_AUTHOR_DATE": "2026-11-05T10:00:00+05:30",
    "GIT_COMMITTER_DATE": "2026-11-05T10:00:00+05:30",
}


@dataclass
class Case:
    name: str
    path: Path
    raw: dict[str, Any]

    @property
    def pr(self) -> dict[str, Any]:
        p: dict[str, Any] = self.raw["pr"]
        return p

    @property
    def expected(self) -> dict[str, Any]:
        f = self.path / "expected.json"
        e: dict[str, Any] = json.loads(f.read_text()) if f.exists() else {}
        return e

    @property
    def answers(self) -> dict[int, str]:
        return {int(k): v for k, v in self.raw.get("answers", {}).items()}

    @property
    def sealed(self) -> bool:
        return (self.path / "session.jsonl").exists()


def load_case(path: Path) -> Case:
    return Case(path.name, path, json.loads((path / "case.json").read_text()))


@dataclass
class World:
    case: Case
    author_repo: Path
    reviewer_repo: Path
    pr: PRData
    head: str
    base: str = "origin/main"
    root: str | None = None
    commit: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def session(self) -> Path:
        return self.author_repo.parent / "claude" / "session.jsonl"


def reseal(world: World, old: str, new: str) -> tuple[str, str]:
    """Adversary: rewrite the sealed session, seal again on a new commit, and push it."""
    text = world.session.read_text()
    if old not in text:
        raise ValueError("reseal: text to replace is not in the session")
    world.session.write_text(text.replace(old, new))
    with git_env():
        res = seal(world.author_repo, world.session, "main", key=DEMO_KEY)
        branch = f"pr-{world.pr.number}"
        _git(world.reviewer_repo, "fetch", "-q", "origin", branch)
        _git(world.reviewer_repo, "merge", "-q", "--ff-only", f"origin/{branch}")
    assert res.commit
    return res.sealed.root.hex(), res.commit


@contextmanager
def git_env() -> Iterator[None]:
    old = {k: os.environ.get(k) for k in GIT_ENV}
    os.environ.update(GIT_ENV)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _write(repo: Path, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        p = repo / rel
        if text is None:
            p.unlink(missing_ok=True)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def materialize(case: Case, work: Path) -> World:
    """Build the author's repo (base, PR commit, seal commit) and the reviewer's clone."""
    if work.exists():
        shutil.rmtree(work)
    author = work / "author" / "repo"
    author.mkdir(parents=True)
    root = commit = None
    with git_env():
        _git(author, "init", "-q", "-b", "main")
        _write(author, case.raw["base"])
        _git(author, "add", "-A")
        _git(author, "commit", "-q", "-m", "base")
        _git(author, "checkout", "-q", "-b", f"pr-{case.pr['number']}")
        _write(author, case.raw["head"])
        _git(author, "add", "-A")
        _git(author, "commit", "-q", "-m", case.pr["title"])
        if case.sealed:
            session = work / "author" / "claude" / "session.jsonl"
            session.parent.mkdir(parents=True)
            shutil.copy(case.path / "session.jsonl", session)
            if (case.path / "session").is_dir():
                shutil.copytree(case.path / "session", session.with_suffix(""))
            res = seal(author, session, "main", key=DEMO_KEY)
            root, commit = res.sealed.root.hex(), res.commit
        reviewer = work / "reviewer" / "repo"
        subprocess.run(
            [
                "git",
                "clone",
                "-q",
                "--branch",
                f"pr-{case.pr['number']}",
                str(author),
                str(reviewer),
            ],
            check=True,
            capture_output=True,
        )
    head = _git(reviewer, "rev-parse", "HEAD").strip()
    files = tuple(
        sorted(
            f for f in _git(reviewer, "diff", "--name-only", "origin/main...HEAD").splitlines() if f
        )
    )
    pr = PRData(
        case.pr["number"],
        case.pr["title"],
        case.pr["body"],
        case.pr["author"],
        files,
        tuple(CheckRun(c["name"], c["conclusion"]) for c in case.raw.get("checks", [])),
    )
    return World(case, author, reviewer, pr, head, root=root, commit=commit)
