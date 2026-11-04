"""``flip replay``: play a fixture case end to end and check it against its expected outcome.

``--offline`` runs on FakeSwitch in this process (M2). Without it, the same case runs on
the local Switch server with fresh users and agents (M4; see solo.py).
Writes ``evidence/replay-<mode>-<case>-<time>.log`` and exits 0 only when the outcome
matches ``expected`` in the case file.
"""

import argparse
import datetime as dt
import importlib
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flipside.room.agents import AuthorAgent, AuthorConfig, ReviewerAgent, ReviewerConfig
from flipside.room.run import Result, Script, compare, play
from flipside.room.scenario import World, load_case, materialize
from flipside.room.transport import FakeSwitch, FakeTransport, Rule

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASE = ROOT / "fixtures" / "cases" / "csv-export"
AUTHOR_AGENT_NAME, REVIEWER_AGENT_NAME = "flipside-author-agent", "flipside-reviewer-agent"


class FakeHumans:
    def __init__(self, hub: FakeSwitch, ids: dict[str, str]) -> None:
        self.hub, self.ids = hub, ids

    def say(self, who: str, room: str, body: str, mention_agent: str | None = None) -> str:
        return self.hub.post(self.ids[who], room, body)

    def answer_card(self, who: str, card: str, answer: str) -> None:
        self.hub.answer(self.ids[who], card, answer)


class FakeClock:
    """Offline time: advances one minute per reading, so the page-rule timeout is testable."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 60.0
        return self.now


def run_offline(world: World, log: Callable[[str], None], work: Path) -> Result:
    case = world.case
    hub = FakeSwitch()
    author_u = hub.user("u-author", case.pr["author"])
    reviewer_u = hub.user("u-reviewer", case.pr.get("reviewer", "reviewer"))
    a_agent = hub.agent("a-author", AUTHOR_AGENT_NAME, author_u)
    r_agent = hub.agent("a-reviewer", REVIEWER_AGENT_NAME, reviewer_u)
    shared = hub.room(f"pr-{world.pr.number}", [author_u, reviewer_u, a_agent, r_agent])
    private = hub.room(f"pr-{world.pr.number}-author", [author_u, a_agent])
    hub.set_policy(
        a_agent,
        [Rule(owner=True, owner_agents=True), Rule(agents=(r_agent,), rooms=(shared,))],
        by=author_u,
    )
    log(
        f"offline Switch: rooms {shared} (shared) and {private} (author only); author-agent "
        "policy: owner, owner's agents, reviewer-agent in the shared room"
    )
    at, rt = FakeTransport(hub, a_agent), FakeTransport(hub, r_agent)
    author = AuthorAgent(
        at,
        AuthorConfig(
            pr=world.pr.number,
            shared=shared,
            private=private,
            repo=world.author_repo,
            root=world.root or "",
            commit=world.commit or "",
            reviewer_agent=r_agent,
            author_user=author_u,
            author_name=case.pr["author"],
            state_path=work / "author-agent.json",
        ),
        log=log,
    )
    reviewer = ReviewerAgent(
        rt,
        ReviewerConfig(
            pr=world.pr,
            shared=shared,
            repo=world.reviewer_repo,
            head=world.head,
            base=world.base,
            author_agent=a_agent,
            author_agent_name=AUTHOR_AGENT_NAME,
            pr_author=author_u,
            reviewer_name=case.pr.get("reviewer", "reviewer"),
            timeout=float(case.raw.get("timeout", 1800)),
        ),
        log=log,
        clock=FakeClock(),
    )
    script = Script(
        world,
        FakeHumans(hub, {"author": author_u, "reviewer": reviewer_u}),
        author,
        reviewer,
        at,
        rt,
        shared,
        AUTHOR_AGENT_NAME,
        log,
    )
    if not world.commit:
        author_steps = author.step
        author.step = lambda: 0  # type: ignore[method-assign]
        del author_steps
    return play(world, author, reviewer, script, lambda: hub.read(author_u, shared), log)


def report(result: Result, expected: dict[str, Any], log: Callable[[str], None]) -> list[str]:
    log("--- transcript")
    for row in result.transcript:
        first = row["body"].splitlines()[0] if row["body"] else ""
        log(f"{row['id']} {row['sender']}: {first}")
    log("--- refusals")
    r = result.refusals
    for name, items in (
        ("Switch refusal (reviewer tags author-agent)", r.switch_refusal),
        ("free-text request dropped", r.dropped_request),
        ("forged disclosure refused", r.forged_verdict),
        ("reviewer answers the card (403)", r.card_403),
    ):
        log(f"{name}: {len(items)}" + "".join(f"\n    {x}" for x in items))
    summary = result.summary()
    log("--- summary " + json.dumps(summary, sort_keys=True))
    diffs = compare(summary, expected)
    for d in diffs:
        log(f"MISMATCH {d}")
    return diffs


def fixtures_report(out: Path) -> int:
    """M5: run every case in fixtures/cases offline and write the results table."""
    cases = sorted((ROOT / "fixtures" / "cases").iterdir())
    rows, failures = [], 0
    for d in cases:
        case = load_case(d)
        with tempfile.TemporaryDirectory(prefix="flip-fixture-") as tmp:
            world = materialize(case, Path(tmp) / "world")
            result = run_offline(world, lambda _m: None, Path(tmp))
        s, exp = result.summary(), case.expected
        hidden = exp.get("hidden", [])
        asked_files = {q[1] for q in s["questions"]}
        surfaced = "n/a" if not hidden else ("yes" if set(hidden) <= asked_files else "NO")
        false_flags = len(s["questions"]) if not hidden else 0
        ok = not compare(s, exp) and result.brief is not None
        failures += not ok
        codes = ", ".join(f"{k} {v}" for k, v in sorted(s["verdicts"].items())) or "none"
        asked = ", ".join(f"{q[0]} {q[1] or ''}".strip() for q in s["questions"]) or "none"
        rows.append(
            f"| {d.name} | {asked} "
            f"| {surfaced} | {codes} | {s['withheld']} | "
            f"{', '.join(s['contradictions']) or 'none'} | {result.false_approvals} | "
            f"{false_flags} | {'PASS' if ok else 'FAIL'} |"
        )
        print(rows[-1])
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(
            [
                "# Fixture results",
                "",
                f"Generated by `make fixtures` on {stamp} IST, offline on FakeSwitch.",
                "Every case is synthetic; `fixtures/build_fixtures.py` writes them.",
                "A hidden change is surfaced when a question names its file.",
                "A false approval is an `OK` verdict on a forged or re-sealed disclosure.",
                "A false flag is a question on an honest PR.",
                "",
                "| Case | Questions | Hidden change surfaced | Verdicts | Withheld "
                "| Contradictions | False approvals | False flags | Matches expected |",
                "|---|---|---|---|---|---|---|---|---|",
                *rows,
                "",
            ]
        )
    )
    print(f"wrote {out.relative_to(ROOT)}; {len(cases) - failures}/{len(cases)} match")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    if argv[:1] == ["--fixtures"]:
        return fixtures_report(ROOT / "docs" / "results" / "fixtures.md")
    p = argparse.ArgumentParser(prog="flip replay")
    p.add_argument("--offline", action="store_true", help="run on FakeSwitch in this process")
    p.add_argument("--case", default=str(DEFAULT_CASE))
    p.add_argument("--work", help="working directory (default: a temp dir)")
    p.add_argument("--no-evidence", action="store_true")
    a = p.parse_args(argv)
    case = load_case(Path(a.case))
    mode = "offline" if a.offline else "switch"
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = ROOT / "evidence" / f"replay-{mode}-{case.name}-{stamp}.log"
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        lines.append(msg)

    with tempfile.TemporaryDirectory(prefix="flip-replay-") as tmp:
        work = Path(a.work) if a.work else Path(tmp)
        world = materialize(case, work / "world")
        log(
            f"case {case.name}: PR #{world.pr.number} {world.pr.title!r}; files "
            f"{', '.join(world.pr.files)}; seal commit {world.commit or 'none'}"
        )
        if a.offline:
            result = run_offline(world, log, work)
        else:
            solo = importlib.import_module("flipside.room.solo")
            result = solo.run_switch(world, log, work)
        diffs = report(result, case.expected, log)
    ok = not diffs and result.brief is not None
    log(f"RESULT {'PASS' if ok else 'FAIL'} {case.name} ({mode}, {result.rounds} rounds)")
    if not a.no_evidence:
        log_path.parent.mkdir(exist_ok=True)
        log_path.write_text("\n".join(lines) + "\n")
        print(f"evidence {log_path.relative_to(ROOT)}")
    return 0 if ok else 1
