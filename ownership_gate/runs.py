"""Verification runs in a session, each with the outcome the evidence supports.

A shell line's exit code belongs to its last command. When a check is piped into `tail`
or followed by `;`, the exit code says nothing about the check, so the outcome is read
from its output, and stays unknown when the output says neither. In a failed `a && b`
line only the output can say which check failed; without it, the last check takes the
failure and the earlier ones stay unknown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ownership_gate.commands import Check, CheckKind, classify_all, cwd_after
from ownership_gate.transcript import Session, Step

FAILED_OUTPUT = re.compile(
    r"\b[1-9]\d* (?:failed|failing|errors?)\b|^FAILED\b|^FAIL\b|Tests?:\s+[1-9]\d* failed"
    r"|Found [1-9]\d* errors?|^error(?:\[|:)",
    re.IGNORECASE | re.MULTILINE,
)
FAILED_TESTS = re.compile(r"\b[1-9]\d* (?:failed|failing)\b|^FAILED\b|^FAIL\b", re.MULTILINE)
PASSED_OUTPUT = re.compile(
    r"\b[1-9]\d* passed\b|All checks passed|Tests?:\s+\d+ passed|\b0 errors\b|^ok\b|\bPASS\b",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class Run:
    step: Step
    check: Check
    ok: bool | None


def runs(session: Session) -> list[Run]:
    found: list[Run] = []
    cwd = ""
    for step in session.commands():
        checks = classify_all(step.command, cwd)
        found += [
            Run(step, check, _outcome(step, check, is_last=i == len(checks) - 1, peers=checks))
            for i, check in enumerate(checks)
        ]
        cwd = cwd_after(step.command, cwd)
    return found


def _outcome(step: Step, check: Check, *, is_last: bool, peers: list[Check]) -> bool | None:
    if step.ok is None:
        return None
    if step.ok is False:
        return _failed_line_outcome(step, check, is_last, peers)
    if check.exit_is_own:
        return True
    if FAILED_OUTPUT.search(step.output):
        return False
    return True if PASSED_OUTPUT.search(step.output) else None


def _failed_line_outcome(
    step: Step, check: Check, is_last: bool, peers: list[Check]
) -> bool | None:
    if len(peers) == 1:
        return False
    tests_failed = FAILED_TESTS.search(step.output) is not None
    if check.kind is CheckKind.TEST and tests_failed:
        return False
    if any(p.kind is CheckKind.TEST for p in peers) and tests_failed:
        return None
    return False if is_last else None
