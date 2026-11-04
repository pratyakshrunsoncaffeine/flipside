"""The gate for one PR: questions, the author's answers with every revision, and status.

A gate is immutable; each answer returns a new gate. Only the PR author may answer.
The gate clears when every question has an answer whose latest revision has no
contradiction. Unverified claims do not block; the reviewer sees them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

from ownership_gate.contradictions import Finding, Verdict, check_answer
from ownership_gate.gaps import Gap, GapReport
from ownership_gate.transcript import Session

# `1: ...` or `Q1.`; a bare `2)` or `3.5` inside an answer is list text, not a new answer.
ANSWER_PREFIX = re.compile(
    r"^\s*(?:Q(\d+)\s*[:.)]|(\d+)\s*:)(?:\s+|$)", re.IGNORECASE | re.MULTILINE
)


class Status(StrEnum):
    AWAITING_ANSWERS = "awaiting_answers"
    CONTRADICTED = "contradicted"
    CLEARED = "cleared"


class NotAuthorError(PermissionError):
    """Raised when someone other than the PR author tries to answer."""


@dataclass(frozen=True)
class Revision:
    question: int
    text: str
    findings: tuple[Finding, ...]

    @property
    def contradicted(self) -> bool:
        return any(f.verdict is Verdict.CONTRADICTED for f in self.findings)


@dataclass(frozen=True)
class Gate:
    report: GapReport
    session: Session | None
    questions: tuple[Gap, ...]
    revisions: tuple[Revision, ...] = ()

    @classmethod
    def open(cls, report: GapReport, session: Session | None) -> Gate:
        return cls(report=report, session=session, questions=report.questions())

    @property
    def author(self) -> str:
        return self.report.pr.author

    def latest(self, question: int) -> Revision | None:
        found = [r for r in self.revisions if r.question == question]
        return found[-1] if found else None

    def history(self, question: int) -> tuple[Revision, ...]:
        return tuple(r for r in self.revisions if r.question == question)

    @property
    def status(self) -> Status:
        latest = [self.latest(i) for i in range(1, len(self.questions) + 1)]
        if any(r is not None and r.contradicted for r in latest):
            return Status.CONTRADICTED
        if any(r is None for r in latest):
            return Status.AWAITING_ANSWERS
        return Status.CLEARED

    def unanswered(self) -> list[int]:
        return [i for i in range(1, len(self.questions) + 1) if self.latest(i) is None]

    def answer(self, sender: str, message: str) -> tuple[Gate, tuple[Revision, ...]]:
        """Record the author's answers in `message`; return the new gate and the new revisions."""
        if sender.casefold() != self.author.casefold():
            raise NotAuthorError(f"Only {self.author} can answer for this PR.")
        new = tuple(
            Revision(question=q, text=text, findings=check_answer(text, self.session))
            for q, text in self._split(message).items()
        )
        return replace(self, revisions=self.revisions + new), new

    def open_questions(self) -> list[int]:
        """Questions still needing an answer: unanswered, or answered with a contradiction."""
        return [
            i
            for i in range(1, len(self.questions) + 1)
            if (r := self.latest(i)) is None or r.contradicted
        ]

    def _split(self, message: str) -> dict[int, str]:
        """Answers by number. Markers count only at line starts, in increasing order, and
        the first must open the message, so a `2)` inside answer 1 stays text and chat
        such as "brb" is never taken as an answer."""
        valid = range(1, len(self.questions) + 1)
        marks, last = [], 0
        for mark in ANSWER_PREFIX.finditer(message):
            number = int(mark.group(1) or mark.group(2))
            opens_message = message[: mark.start()].strip() == ""
            if number in valid and number > last and (marks or opens_message):
                marks.append(mark)
                last = number
        if not marks:
            return {}
        parts: dict[int, str] = {}
        for mark, nxt in zip(marks, [*marks[1:], None], strict=True):
            end = nxt.start() if nxt else len(message)
            text = message[mark.end() : end].strip()
            if text:
                parts[int(mark.group(1) or mark.group(2))] = text
        return parts
