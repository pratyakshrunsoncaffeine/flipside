"""Chat text the gate posts. Plain Markdown, which Mattermost, Slack and Discord all render."""

from __future__ import annotations

from ownership_gate.contradictions import Verdict
from ownership_gate.gate import Gate, Revision, Status

NO_TRAIL = (
    "**No trail.** This PR has no linked agent session, so only CI and size were checked. "
    "The reviewer will see it as unverified."
)
ANSWER_HINT = "Start each answer with its number, like `1: ...`, so it goes on the record."
ZERO_WIDTH_SPACE = "​"
OPENING_PREFIX = "**Ownership Gate for "


def is_opening(text: str) -> bool:
    """Whether a posted message is a gate's opening, which starts a new round of answers."""
    return text.startswith(OPENING_PREFIX)


def opening(gate: Gate, handle: str = "") -> str:
    pr = gate.report.pr
    handle = handle or pr.author
    lines = [f"{OPENING_PREFIX}{pr.key}: {_inline(pr.title)}**"]
    if not gate.report.has_trail:
        lines.append(NO_TRAIL)
    if not gate.questions:
        lines.append("No gaps found between the PR, the session and CI.")
        return "\n\n".join(lines)
    lines.append(
        f"@{handle}, before a reviewer is paged, answer these in your own words. "
        "Reply `1: ...`, `2: ...`. Your answers stay on the record, edits included."
    )
    lines.append("\n".join(f"{i}. {q.question}" for i, q in enumerate(gate.questions, 1)))
    if extra := _unasked(gate):
        lines.append(f"_{extra} more gap(s) were found; the reviewer will see them._")
    return "\n\n".join(lines)


def checked(gate: Gate, revisions: tuple[Revision, ...], handle: str = "") -> str:
    handle = handle or gate.author
    lines = []
    for rev in revisions:
        for f in rev.findings:
            label = "Contradiction" if f.verdict is Verdict.CONTRADICTED else "Unverified"
            claim = _inline(f.claim.rstrip("."))
            lines.append(f'**{label} in answer {rev.question}.** You wrote: "{claim}". {f.message}')
    if gate.status is Status.CONTRADICTED:
        lines.append(f"@{handle}, revise the answers marked as contradictions.")
    elif gate.status is Status.AWAITING_ANSWERS:
        lines.append(f"Still open: {', '.join(str(i) for i in gate.unanswered())}.")
    elif not lines:
        lines.append("No contradictions left.")
    return "\n\n".join(lines)


def revised_after_paging(gate: Gate, revisions: tuple[Revision, ...], reviewer: str) -> str:
    mention = f"@{reviewer}, " if reviewer else ""
    numbers = ", ".join(str(r.question) for r in revisions)
    state = "and it now has a contradiction" if gate.status is Status.CONTRADICTED else ""
    return (
        f"{mention}the author revised answer {numbers} after you were paged {state}".strip() + "."
    )


def reviewer_brief(gate: Gate, reviewer: str = "", handle: str = "") -> str:
    pr = gate.report.pr
    handle = handle or pr.author
    mention = f"@{reviewer} " if reviewer else ""
    trail = "linked session checked" if gate.report.has_trail else "no trail, unverified"
    title = _inline(pr.title)
    lines = [f"{mention}**{pr.key} is ready for review.** {title} by @{handle} ({trail})."]
    for i, q in enumerate(gate.questions, 1):
        history = gate.history(i)
        lines.append(f"**{i}. {q.question}**")
        lines.append(_quote(history[-1].text) if history else "> (no answer)")
        if len(history) > 1:
            lines.append(
                f"_Revised {len(history) - 1} time(s); earlier answers are in the thread._"
            )
        unverified = [f for f in history[-1].findings if f.verdict is Verdict.UNVERIFIED]
        lines += [f"_Unverified: {_inline(f.claim)}_" for f in unverified]
    unasked = gate.report.questions(limit=len(gate.report.gaps))[len(gate.questions) :]
    lines += [f"_Also found, not asked: {g.question}_" for g in unasked]
    if not gate.questions:
        lines.append("No gaps found.")
    return "\n\n".join(lines)


def _unasked(gate: Gate) -> int:
    return len(gate.report.gaps) - len(gate.questions)


def _quote(text: str) -> str:
    """Quote every line, so an answer cannot break out of the quote or ping anyone."""
    return "\n".join(f"> {_inline(line)}" for line in text.splitlines() or [""])


def _inline(text: str) -> str:
    return text.replace("@", "@" + ZERO_WIDTH_SPACE)
