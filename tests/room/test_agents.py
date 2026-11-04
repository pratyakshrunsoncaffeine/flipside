"""Agent behaviour offline: restart without duplicates, the page-rule timeout, secret scan."""

import json
from pathlib import Path
from typing import Any

from flipside.room import replay
from flipside.room.agents import AuthorAgent, AuthorConfig, ReviewerAgent, ReviewerConfig
from flipside.room.protocol import decode
from flipside.room.scenario import World, load_case, materialize
from flipside.room.transport import FakeSwitch, FakeTransport, Rule

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "fixtures" / "cases" / "csv-export"


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def setup(world: World, tmp: Path, clock: Clock) -> dict[str, Any]:
    hub = FakeSwitch()
    au, ru = hub.user("a", "priya"), hub.user("r", "omar")
    aa = hub.agent("aa", replay.AUTHOR_AGENT_NAME, au)
    ra = hub.agent("ra", replay.REVIEWER_AGENT_NAME, ru)
    hub.room("pr", [au, ru, aa, ra])
    hub.room("priv", [au, aa])
    hub.set_policy(aa, [Rule(owner=True), Rule(agents=(ra,), rooms=("pr",))], by=au)

    def author() -> AuthorAgent:
        return AuthorAgent(
            FakeTransport(hub, aa),
            AuthorConfig(
                world.pr.number,
                "pr",
                "priv",
                world.author_repo,
                world.root or "",
                world.commit or "",
                ra,
                au,
                "priya",
                tmp / "author-state.json",
            ),
            log=lambda _m: None,
        )

    def reviewer() -> ReviewerAgent:
        return ReviewerAgent(
            FakeTransport(hub, ra),
            ReviewerConfig(
                world.pr,
                "pr",
                world.reviewer_repo,
                world.head,
                world.base,
                aa,
                replay.AUTHOR_AGENT_NAME,
                au,
                "omar",
                timeout=600,
            ),
            log=lambda _m: None,
            clock=clock,
        )

    return {"hub": hub, "au": au, "author": author, "reviewer": reviewer}


def types(hub: FakeSwitch) -> list[str]:
    return [o["t"] for m in hub.messages if (o := decode(m.body))]


def test_restart_each_agent_mid_flow_without_duplicate_posts(tmp_path: Path) -> None:
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    hub = s["hub"]
    a, r = s["author"](), s["reviewer"]()
    a.step()
    r.step()
    assert types(hub) == ["seal", "questions", "request"]
    a, r = s["author"](), s["reviewer"]()  # both restart
    a.step()
    r.step()
    assert types(hub) == ["seal", "questions", "request"]
    assert len(hub.cards) == 1
    a = s["author"]()  # restart after the card opened; state file holds it
    a.step()
    assert len(hub.cards) == 1
    hub.post(s["au"], "pr", "Q1: the export test needed a longer session")
    hub.answer(s["au"], next(iter(hub.cards)), "approve")
    a.step()
    a = s["author"]()
    a.step()
    r = s["reviewer"]()
    r.step()
    r = s["reviewer"]()
    r.step()
    assert types(hub) == ["seal", "questions", "request", "disclosure", "verdict", "brief"]


def test_timeout_posts_brief_with_no_answer(tmp_path: Path) -> None:
    world = materialize(load_case(CSV), tmp_path / "w")
    clock = Clock()
    s = setup(world, tmp_path, clock)
    hub = s["hub"]
    a, r = s["author"](), s["reviewer"]()
    a.step()
    r.step()
    a.step()
    r.step()
    assert "brief" not in types(hub)
    clock.t = 601
    r.step()
    brief = next(o for m in hub.messages if (o := decode(m.body)) and o["t"] == "brief")
    assert brief["gaps"][0]["answer"] == "no answer"
    assert brief["gaps"][0]["verdicts"] == []


def test_secret_leaf_is_withheld_without_a_card(tmp_path: Path) -> None:
    case = load_case(CSV)
    work = tmp_path / "case"
    work.mkdir()
    raw = json.loads((CSV / "case.json").read_text())
    (work / "case.json").write_text(json.dumps(raw))
    text = (
        (CSV / "session.jsonl")
        .read_text()
        .replace(
            "raising SESSION_TTL to 86400",
            "raising SESSION_TTL to 86400; DB_PASSWORD=Zx9q2LmP7vR4tY8kW3nB",
        )
    )
    (work / "session.jsonl").write_text(text)
    world = materialize(load_case(work), tmp_path / "w")
    assert case.name == "csv-export"
    s = setup(world, tmp_path, Clock())
    hub = s["hub"]
    a, r = s["author"](), s["reviewer"]()
    for _ in range(3):
        a.step()
        r.step()
    withheld = [o for m in hub.messages if (o := decode(m.body)) and o["t"] == "withheld"]
    assert [w["reason"] for w in withheld] == ["secret_scan"]
    assert hub.cards == {}
    assert all("Zx9q2LmP7vR4tY8kW3nB" not in m.body for m in hub.messages)
