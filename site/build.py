"""Turn one `make demo` evidence log into the script the site plays: site/run.js.

Every message step keeps its Switch message id, so the page replays a real run and nothing
in it is invented. Steps are grouped into the chapters of the review, in this order:
seal, question, answer, refusals, approval, proof, forgery, brief.

    python3 site/build.py evidence/demo-mattermost-<case>-<time>.log

Standard library only; deterministic for a given log.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "run.js"

CHAPTERS = [
    ("seal", "The author's agent seals its session. The session itself stays on the laptop."),
    ("question", "The reviewer's agent asks about one step."),
    ("answer", "The author replies in their own words, straight from Mattermost."),
    ("refuse", "Anyone else who asks the author's agent is turned away by Switch."),
    ("approve", "The step goes to the author first. It reaches the reviewer only after they approve."),
    ("proof", "The reviewer's agent checks the step against the seal. It matches."),
    ("forgery", "Change one word and the check fails."),
    ("brief", "The reviewer gets a short brief, not the session."),
]

_LINE = re.compile(r"^\d\d:\d\d:\d\d (sw_[0-9a-f]+) ([^:]+): (.*)$")
_SEAL = re.compile(r"root (\w+) · (\d+) leaves · commit (\w+)")
_LEAF = re.compile(r"leaf (\d+)")
_REQ = re.compile(r"requesting leaves ([\d, ]+)")


def _section(lines: list[str], name: str) -> list[str]:
    out: list[str] = []
    inside = False
    for ln in lines:
        if re.match(rf"^\S+ --- {name}\b", ln):
            inside = True
            continue
        if inside and re.match(r"^\S+ --- ", ln):
            break
        if inside:
            out.append(ln)
    return out


def classify(
    sender: str, text: str, injected: set[str], forged: set[str], sw: str
) -> tuple[str, str] | None:
    """(chapter, kind) for one transcript line, or None for lines the story skips."""
    if sw in injected:
        return "refuse", "injection"
    if sw in forged:
        return "forgery", "forged"
    if "not permitted to direct messages" in text or "isn't linked to a Switch user" in text:
        return "refuse", "switch-refusal"
    if sender.endswith("-person"):
        return ("answer", "human") if re.search(r"\bQ\d+:", text) else ("refuse", "human-tag")
    rules = [  # first match wins: "Brief for PR #" must be tested before "for PR #"
        ("Brief for PR", "brief", "brief"),
        ("manifest.json", "seal", "attachment"),
        ("Seal for PR", "seal", "seal"),
        ("for PR #", "question", "questions"),
        ("requesting leaves", "question", "request"),
        ("answered Q", "answer", "relay"),
        ("approved by @", "proof", "disclosure"),
        ("PROOF_FAIL", "forgery", "verdict-fail"),
        (" · OK leaf", "proof", "verdict-ok"),
    ]
    for needle, chapter, kind in rules:
        if needle in text:
            return chapter, kind
    return None  # greetings and anything else Switch posted on its own


def build(log: str, source: str) -> dict[str, Any]:
    lines = log.splitlines()
    injected = set(re.findall(r"posted an injection request (sw_[0-9a-f]+)", log))
    forged = set(re.findall(r"posted a forged disclosure (sw_[0-9a-f]+)", log))
    steps: dict[str, list[dict[str, Any]]] = {c: [] for c, _ in CHAPTERS}
    seal: dict[str, Any] = {}
    for ln in _section(lines, "transcript"):
        m = _LINE.match(ln)
        if not m:
            continue
        sw, sender, text = m.groups()
        got = classify(sender, text, injected, forged, sw)
        if got is None:
            continue
        chapter, kind = got
        step: dict[str, Any] = {
            "kind": kind,
            "room": "shared",
            "who": sender,
            "text": text,
            "sw": sw,
        }
        if kind == "seal" and (s := _SEAL.search(text)):
            seal = {"root": s.group(1), "leaves": int(s.group(2)), "commit": s.group(3)}
        if kind == "request" and (r := _REQ.search(text)):
            step["leaves"] = [int(x) for x in r.group(1).replace(",", " ").split()]
        if kind.startswith("verdict") and (lf := _LEAF.search(text)):
            step["leaf"] = int(lf.group(1))
        steps[chapter].append(step)

    disclosed = next((s for s in steps["proof"] if s["kind"] == "disclosure"), None)
    where = re.search(r"step (\d+), chunk (\d+)", disclosed["text"]) if disclosed else None
    leaf = next((s["leaves"][0] for s in steps["question"] if s.get("leaves")), None)
    card = (
        f"Disclose step {where.group(1)}, chunk {where.group(2)} to the review room?"
        if where
        else ""
    )
    approval: list[dict[str, Any]] = []
    if card:
        approval.append(
            {
                "kind": "card",
                "room": "private",
                "who": "flipside-author-agent",
                "text": card,
                "leaf": leaf,
                "reconstructed": True,
            }
        )
    for m in re.finditer(r"reviewer answering card (\w+) refused: (.*)", log):
        approval.append(
            {
                "kind": "card-403",
                "room": "private",
                "who": "reviewer",
                "card": m.group(1),
                "text": m.group(2),
                "reconstructed": True,
            }
        )
    for m in re.finditer(r"author pressed (\w+) on card (\w+) in Mattermost", log):
        approval.append(
            {
                "kind": "press",
                "room": "private",
                "who": "author-person",
                "card": m.group(2),
                "text": m.group(1),
                "reconstructed": True,
            }
        )
    steps["approve"] = approval

    case = re.search(r"case ([\w-]+): PR #(\d+) '([^']*)'; seal commit (\w+)", log)
    result = re.search(r"RESULT (PASS|FAIL) ", log)
    kills = len(re.findall(r"killed with SIGKILL", log))
    dups = re.search(r"duplicate agent posts: (\d+)", log)
    chapters = [{"id": c, "caption": cap, "steps": steps[c]} for c, cap in CHAPTERS if steps[c]]
    return {
        "source": source,
        "case": case.group(1) if case else "",
        "pr": int(case.group(2)) if case else 0,
        "title": case.group(3) if case else "",
        "seal": seal,
        "result": result.group(1) if result else "",
        "restarts": kills,
        "duplicates": int(dups.group(1)) if dups else None,
        "chapters": chapters,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[-3].strip(), file=sys.stderr)
        return 2
    path = Path(argv[0]).resolve()
    run = build(path.read_text(encoding="utf-8"), path.relative_to(ROOT).as_posix())
    body = json.dumps(run, ensure_ascii=False, indent=1)
    OUT.write_text(
        f"// Generated by site/build.py from {run['source']}. Do not edit.\nwindow.RUN = {body};\n",
        encoding="utf-8",
        newline="",
    )
    n = sum(len(c["steps"]) for c in run["chapters"])
    print(f"{OUT.relative_to(ROOT)}: {n} steps in {len(run['chapters'])} chapters")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
