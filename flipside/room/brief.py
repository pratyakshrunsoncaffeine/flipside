"""The brief reviewer-agent posts when the page rule fires (docs/DESIGN.md 3 step 11, 5.5)."""

from collections.abc import Sequence
from typing import Any

from flipside.room.rules import Contradiction, Gap, PRData, Selection
from flipside.seal.coverage import coverage, format_line


def build_brief(
    pr: PRData,
    commit: str,
    seal_note: str,
    manifest: Sequence[dict[str, Any]] | None,
    qs: Sequence[Gap],
    not_asked: Sequence[Gap],
    sel: dict[int, Selection],
    answers: dict[int, str],
    verdicts: Sequence[dict[str, Any]],
    withheld: Sequence[dict[str, Any]],
    found: Sequence[Contradiction],
    reviewer: str,
) -> tuple[str, dict[str, Any]]:
    """Return the human line (mentions the reviewer) and the brief JSON."""
    ok = sorted({v["i"] for v in verdicts if v["code"] == "OK"})
    cov = coverage(manifest or [], ok, list(pr.files))
    gaps_out = []
    for k, g in enumerate(qs, 1):
        gaps_out.append(
            {
                "q": k,
                "gap": g.kind,
                "file": g.file,
                "check": g.check,
                "text": g.text,
                "answer": answers.get(k, "no answer"),
                "requested": list(sel[k].leaves),
                "verdicts": [{"i": v["i"], "code": v["code"]} for v in verdicts if v["q"] == k],
                "withheld": [{"i": w["i"], "reason": w["reason"]} for w in withheld if w["q"] == k],
            }
        )
    fails = [v for v in verdicts if v["code"] != "OK"]
    obj: dict[str, Any] = {
        "t": "brief",
        "v": 1,
        "commit": commit,
        "pr": pr.number,
        "seal": seal_note,
        "gaps": gaps_out,
        "not_asked": [{"gap": g.kind, "file": g.file, "text": g.text} for g in not_asked],
        "coverage": [{**c.to_json(), "line": format_line(c)} for c in cov],
        "contradictions": [{"rule": c.rule, "q": c.q, "i": c.i, "detail": c.detail} for c in found],
        "refused": [{"q": v["q"], "i": v["i"], "code": v["code"]} for v in fails],
    }
    answered = sum(1 for k in range(1, len(qs) + 1) if k in answers)
    line = (
        f"@{reviewer} Brief for PR #{pr.number}: {len(qs)} question"
        f"{'s' if len(qs) != 1 else ''}, {answered} answered, {len(ok)} "
        f"lea{'f' if len(ok) == 1 else 'ves'} verified, "
        f"{len(withheld)} withheld, {len(fails)} refused, {len(found)} contradiction"
        f"{'s' if len(found) != 1 else ''}"
    )
    return line, obj
