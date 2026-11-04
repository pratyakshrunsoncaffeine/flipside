"""Checks the author's own answer against their session.

The author writes in their own words. When a clause of an answer says something ran or
passed, the checker finds the session's runs of related checks. A related run that
failed, with no later passing run that covers it, is a contradiction, cited by step.
If no related run exists the claim is only unverified: the work may have happened
outside the agent, so it is shown to the reviewer, not blocked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ownership_gate.commands import CheckKind, covers, display_command
from ownership_gate.runs import Run, runs
from ownership_gate.transcript import Session

RAN_CLAIM = re.compile(
    r"\b(?:tested|ran|run|re-?ran|re-?run|verified|checked|pass|passes|passed|passing|green"
    r"|works|fixed|clean)\b",
    re.IGNORECASE,
)
NEGATION = re.compile(
    r"\b(?:not|never|no|without|cannot|unable)\b|\w+n't\b|\bcan't\b|\bwon't\b", re.IGNORECASE
)
CLAUSE_BREAK = re.compile(r",?\s+but\s+|;\s*|,\s+(?:although|though|except)\s+", re.IGNORECASE)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
SUITE_WORDS = re.compile(r"\b(?:all|full|whole|entire|everything|suite)\b", re.IGNORECASE)
WORD = re.compile(r"[a-z][a-z0-9]{3,}")
STOPWORDS = frozenset(
    {
        "tested",
        "test",
        "tests",
        "testing",
        "pass",
        "passes",
        "passed",
        "passing",
        "green",
        "works",
        "that",
        "this",
        "with",
        "from",
        "have",
        "were",
        "they",
        "them",
        "then",
        "after",
        "before",
        "locally",
        "again",
        "fixed",
        "checked",
        "verified",
        "really",
        "also",
        "there",
        "which",
        "what",
        "when",
        "rerun",
        "reran",
        "just",
        "made",
        "sure",
        "clean",
        "now",
        "both",
        "each",
        "every",
        "still",
        "should",
        "would",
        "could",
        "their",
        "your",
    }
)
KIND_PATTERNS = {
    CheckKind.TEST: re.compile(r"\btest|\bspecs?\b|\bsuite\b", re.IGNORECASE),
    CheckKind.LINT: re.compile(r"\blint|\bruff\b|\beslint\b|\bflake8\b", re.IGNORECASE),
    CheckKind.TYPECHECK: re.compile(
        r"\btype[- ]?check|\btypes\b|\bmypy\b|\btsc\b|\bpyright\b", re.IGNORECASE
    ),
    CheckKind.BUILD: re.compile(r"\bbuilds?\b|\bcompiles?\b", re.IGNORECASE),
}


class Verdict(StrEnum):
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class Finding:
    verdict: Verdict
    claim: str
    message: str
    step: int | None = None


def check_answer(answer: str, session: Session | None) -> tuple[Finding, ...]:
    """Return findings for every clause of `answer` that claims something ran or passed."""
    session_runs = None if session is None else runs(session)
    findings = (_check_clause(c, session_runs) for c in _clauses(answer))
    return tuple(f for f in findings if f is not None)


def _clauses(text: str) -> list[str]:
    return [
        c.strip()
        for sentence in SENTENCE_BREAK.split(text)
        for c in CLAUSE_BREAK.split(sentence)
        if c.strip()
    ]


def _check_clause(clause: str, session_runs: list[Run] | None) -> Finding | None:
    if not RAN_CLAIM.search(clause) or NEGATION.search(clause):
        return None
    kinds = {kind for kind, pattern in KIND_PATTERNS.items() if pattern.search(clause)}
    if not kinds:
        return None
    if session_runs is None:
        return Finding(Verdict.UNVERIFIED, clause, "This PR has no session trail to check it.")
    related = _related(clause, kinds, session_runs)
    if not related:
        return Finding(
            Verdict.UNVERIFIED,
            clause,
            "Your session has no matching run, so the reviewer will see this as unverified.",
        )
    still_failing = [r for r in related if r.ok is False and not _rerun_later(r, session_runs)]
    if not still_failing:
        return None
    failed = still_failing[-1]
    return Finding(
        Verdict.CONTRADICTED,
        clause,
        step=failed.step.index,
        message=f"Step {failed.step.index} shows `{display_command(failed.step.command)}` "
        "failed, and nothing after it reran it.",
    )


def _related(clause: str, kinds: set[CheckKind], session_runs: list[Run]) -> list[Run]:
    known = [r for r in session_runs if r.check.kind in kinds and r.ok is not None]
    subjects = {w for w in WORD.findall(clause.lower()) if w not in STOPWORDS}
    if SUITE_WORDS.search(clause) or not subjects:
        return known
    return [r for r in known if _mentions(r, subjects)]


def _rerun_later(failed: Run, session_runs: list[Run]) -> bool:
    return any(
        r.ok and r.step.index > failed.step.index and covers(r.check, failed.check)
        for r in session_runs
    )


def _mentions(run: Run, subjects: set[str]) -> bool:
    parts = (*run.check.targets, run.check.tool, run.check.workdir)
    tokens = {t for part in parts for t in re.split(r"[^a-z0-9]+", part.lower()) if len(t) >= 4}
    return any(t.startswith(s) or s.startswith(t) for s in subjects for t in tokens)
