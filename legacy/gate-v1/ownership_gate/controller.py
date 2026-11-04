"""Runs gates for PRs and turns room messages into gate updates.

Transport-free: callers feed it PRs and chat messages and post what it returns. The
Switch agent and the offline demo both drive this same class.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ownership_gate import render
from ownership_gate.gaps import DEFAULT_MAX_LINES, find_gaps
from ownership_gate.gate import Gate, NotAuthorError, Status
from ownership_gate.model import PullRequest
from ownership_gate.transcript import Session


@dataclass
class GateController:
    reviewer: str = ""
    handles: dict[str, str] = field(default_factory=dict)
    max_lines: int = DEFAULT_MAX_LINES
    gates: dict[str, Gate] = field(default_factory=dict)
    paged: set[str] = field(default_factory=set)

    def open(self, pr: PullRequest, session: Session | None) -> list[str]:
        """Open (or reopen on a new head commit) the gate for a PR."""
        gate = Gate.open(find_gaps(pr, session, self.max_lines), session)
        self.gates[pr.key] = gate
        self.paged.discard(pr.key)
        return [render.opening(gate, self._handle(gate)), *self._page_if_cleared(pr.key)]

    def forget(self, pr_key: str) -> None:
        """Drop a PR's gate, so the next `open` starts it afresh."""
        self.gates.pop(pr_key, None)
        self.paged.discard(pr_key)

    def is_current(self, pr: PullRequest) -> bool:
        return self.head_sha(pr.key) == pr.head_sha

    def head_sha(self, pr_key: str) -> str | None:
        """The head commit the PR's gate was opened on, if it has one."""
        gate = self.gates.get(pr_key)
        return None if gate is None else gate.report.pr.head_sha

    def on_message(self, pr_key: str, sender: str, text: str) -> list[str]:
        gate = self.gates.get(pr_key)
        if gate is None:
            return []
        try:
            gate, revisions = gate.answer(sender, text)
        except NotAuthorError as err:
            return [str(err)]
        if not revisions:
            return [render.ANSWER_HINT] if gate.questions else []
        self.gates[pr_key] = gate
        replies = [render.checked(gate, revisions, self._handle(gate))]
        if pr_key in self.paged:
            replies.append(render.revised_after_paging(gate, revisions, self.reviewer))
        return [*replies, *self._page_if_cleared(pr_key)]

    def status(self, pr_key: str) -> Status | None:
        gate = self.gates.get(pr_key)
        return None if gate is None else gate.status

    def _page_if_cleared(self, pr_key: str) -> list[str]:
        gate = self.gates[pr_key]
        if gate.status is not Status.CLEARED or pr_key in self.paged:
            return []
        self.paged.add(pr_key)
        return [render.reviewer_brief(gate, self.reviewer, self._handle(gate))]

    def _handle(self, gate: Gate) -> str:
        """The author's chat username, when it differs from their GitHub login."""
        return self.handles.get(gate.author.casefold(), gate.author)
