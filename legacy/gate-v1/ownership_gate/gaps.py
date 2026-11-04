"""Deterministic gap checker: what the PR claims versus what the session and CI show.

Every gap carries the question the author must answer and, when it comes from the
session, the step it cites. No LLM is involved, so the same inputs give the same gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from ownership_gate.claims import parse_claims
from ownership_gate.commands import Check, CheckKind, covers, display_command
from ownership_gate.model import PullRequest
from ownership_gate.runs import runs
from ownership_gate.transcript import Session, Step

DEFAULT_MAX_LINES = 400
MAX_QUESTIONS = 5
LOCKFILES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "go.sum",
        "composer.lock",
        "Pipfile.lock",
    }
)
# Words too generic to say which file or area a prompt meant.
GENERIC_WORDS = frozenset(
    {
        "index",
        "main",
        "init",
        "mod",
        "utils",
        "util",
        "helpers",
        "types",
        "constants",
        "config",
        "settings",
        "app",
        "lib",
        "src",
        "test",
        "tests",
        "spec",
        "specs",
        "web",
        "components",
        "pages",
        "core",
        "common",
        "shared",
        "internal",
        "pkg",
        "cmd",
    }
)
MIN_WORD = 4
CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


class GapKind(StrEnum):
    FAILED_NOT_RERUN = "failed_not_rerun"
    TESTS_CLAIMED_NOT_RUN = "tests_claimed_not_run"
    COMMAND_CLAIMED_NOT_RUN = "command_claimed_not_run"
    CI_FAILING = "ci_failing"
    CI_MISSING = "ci_missing"
    UNPROMPTED_FILE = "unprompted_file"
    OVERSIZE = "oversize"


PRIORITY = list(GapKind)


@dataclass(frozen=True)
class Gap:
    kind: GapKind
    question: str
    step: int | None = None
    subject: str = ""


@dataclass(frozen=True)
class GapReport:
    """`has_trail` is False when the PR has no Entire session; CI and size gaps still run."""

    pr: PullRequest
    has_trail: bool
    gaps: tuple[Gap, ...]

    def questions(self, limit: int = MAX_QUESTIONS) -> tuple[Gap, ...]:
        ranked = sorted(self.gaps, key=lambda g: (PRIORITY.index(g.kind), g.step or 0))
        return tuple(ranked[:limit])


def find_gaps(
    pr: PullRequest, session: Session | None, max_lines: int = DEFAULT_MAX_LINES
) -> GapReport:
    claims = parse_claims(pr.body)
    gaps: list[Gap] = []
    if session is not None:
        gaps += _failed_not_rerun(session)
        gaps += _claims_not_run(session, claims.tests_pass, claims.commands)
        gaps += _unprompted_files(pr, session)
    claims_tests = claims.tests_pass or any(c.kind is CheckKind.TEST for _, c in claims.commands)
    gaps += _ci_gaps(pr, claims_tests)
    gaps += _oversize(pr, max_lines)
    return GapReport(pr=pr, has_trail=session is not None, gaps=tuple(gaps))


def _failed_not_rerun(session: Session) -> list[Gap]:
    open_failures: dict[Check, Step] = {}
    for run in runs(session):
        if run.ok is False:
            open_failures[run.check] = run.step
        elif run.ok:
            open_failures = {c: s for c, s in open_failures.items() if not covers(run.check, c)}
    return [
        Gap(
            GapKind.FAILED_NOT_RERUN,
            subject=display_command(step.command),
            step=step.index,
            question=f"Step {step.index} shows `{display_command(step.command)}` failed "
            "and was never rerun. What did you do about that failure?",
        )
        for check, step in sorted(open_failures.items(), key=lambda item: item[1].index)
    ]


def _claims_not_run(
    session: Session, tests_pass: bool, commands: tuple[tuple[str, Check], ...]
) -> list[Gap]:
    session_runs = runs(session)
    passed = [r.check for r in session_runs if r.ok]
    gaps: list[Gap] = []
    if tests_pass and not any(r.check.kind is CheckKind.TEST for r in session_runs):
        gaps.append(
            Gap(
                GapKind.TESTS_CLAIMED_NOT_RUN,
                subject="tests",
                question="The PR says tests pass, but no test command ran in your session. "
                "Which tests did you run, and where?",
            )
        )
    for text, claimed in commands:
        if not any(covers(done, claimed) for done in passed):
            gaps.append(
                Gap(
                    GapKind.COMMAND_CLAIMED_NOT_RUN,
                    subject=text,
                    question=f"The PR says you ran `{text}`. Your session has no passing run "
                    "of it. Where did it run, and what did it print?",
                )
            )
    return gaps


def _ci_gaps(pr: PullRequest, tests_pass: bool) -> list[Gap]:
    sha = pr.head_sha[:7]
    gaps = [
        Gap(
            GapKind.CI_FAILING,
            subject=run.name,
            question=f"CI check `{run.name}` reported {run.conclusion} on {sha}. "
            "Is that expected, and what changes it?",
        )
        for run in pr.checks
        if run.failed
    ]
    if tests_pass and not pr.checks:
        gaps.append(
            Gap(
                GapKind.CI_MISSING,
                subject=sha,
                question=f"The PR says tests were run, but no CI check reported on {sha}. "
                "How were the tests run?",
            )
        )
    return gaps


def _unprompted_files(pr: PullRequest, session: Session) -> list[Gap]:
    context = "\n".join([pr.title, pr.body, *(p.text for p in session.prompts())]).lower()
    return [
        Gap(
            GapKind.UNPROMPTED_FILE,
            subject=f.path,
            question=f"`{f.path}` changed, but neither your prompts nor the PR description "
            "mention it. Why did it change?",
        )
        for f in pr.files
        if not _is_lockfile(f.path) and not _mentioned(f.path, context)
    ]


def _oversize(pr: PullRequest, max_lines: int) -> list[Gap]:
    changed = sum(f.additions + f.deletions for f in pr.files if not _is_lockfile(f.path))
    if changed <= max_lines:
        return []
    return [
        Gap(
            GapKind.OVERSIZE,
            subject=str(changed),
            question=f"This PR changes {changed} lines (limit {max_lines}). Can it be split? "
            "If not, which part should the reviewer read first?",
        )
    ]


def _is_lockfile(path: str) -> bool:
    return PurePosixPath(path).name in LOCKFILES


def _mentioned(path: str, context: str) -> bool:
    """A file counts as mentioned by its path, or by a word of its name or its folder's name."""
    pure = PurePosixPath(path)
    if path.lower() in context or pure.name.lower() in context:
        return True
    return any(re.search(rf"\b{re.escape(w.rstrip('s'))}", context) for w in _name_words(pure))


def _name_words(path: PurePosixPath) -> set[str]:
    words = set()
    for part in (path.stem, path.parent.name):
        for word in re.split(r"[^A-Za-z]+", CAMEL.sub(" ", part)):
            word = word.lower()
            if len(word) >= MIN_WORD and word not in GENERIC_WORDS:
                words.add(word)
    return words
