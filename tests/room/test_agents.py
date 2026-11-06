"""Agent behaviour offline: restart without duplicates, the page-rule timeout, secret scan."""

import json
from pathlib import Path
from typing import Any

from flipside.room import replay
from flipside.room.agents import AuthorAgent, AuthorConfig, ReviewerAgent, ReviewerConfig
from flipside.room.protocol import decode, encode
from flipside.room.scenario import World, load_case, materialize, reseal
from flipside.room.transport import FakeSwitch, FakeTransport, Rule

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "fixtures" / "cases" / "csv-export"


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def setup(
    world: World,
    tmp: Path,
    clock: Clock,
    rooms: tuple[str, str] = ("pr", "priv"),
    answerers: tuple[str, ...] = (),
) -> dict[str, Any]:
    shared, private = rooms
    hub = FakeSwitch()
    au, ru = hub.user("a", "priya"), hub.user("r", "omar")
    aa = hub.agent("aa", replay.AUTHOR_AGENT_NAME, au)
    ra = hub.agent("ra", replay.REVIEWER_AGENT_NAME, ru)
    hub.room(shared, [au, ru, aa, ra])
    hub.room(private, [au, aa])
    hub.set_policy(aa, [Rule(owner=True), Rule(agents=(ra,), rooms=(shared,))], by=au)

    def author() -> AuthorAgent:
        return AuthorAgent(
            FakeTransport(hub, aa),
            AuthorConfig(
                world.pr.number,
                shared,
                private,
                world.author_repo,
                world.root or "",
                world.commit or "",
                ra,
                au,
                "priya",
                tmp / "author-state.json",
                author_answerers=answerers,
            ),
            log=lambda _m: None,
        )

    def reviewer() -> ReviewerAgent:
        return ReviewerAgent(
            FakeTransport(hub, ra),
            ReviewerConfig(
                world.pr,
                shared,
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

    return {"hub": hub, "au": au, "ra": ra, "author": author, "reviewer": reviewer}


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
    raw = json.loads((CSV / "case.json").read_text(encoding="utf-8"))
    (work / "case.json").write_text(json.dumps(raw), encoding="utf-8", newline="")
    text = (
        (CSV / "session.jsonl")
        .read_text(encoding="utf-8")
        .replace(
            "raising SESSION_TTL to 86400",
            "raising SESSION_TTL to 86400; DB_PASSWORD=Zx9q2LmP7vR4tY8kW3nB",
        )
    )
    (work / "session.jsonl").write_text(text, encoding="utf-8", newline="")
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


def test_restart_after_the_session_was_rewritten_withholds_instead_of_crashing(
    tmp_path: Path,
) -> None:
    case = load_case(ROOT / "fixtures" / "cases" / "reseal-after-questions")
    world = materialize(case, tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    hub = s["hub"]
    s["author"]().step()
    s["reviewer"]().step()
    old, new = case.raw["reseal_after_questions"]
    reseal(world, old, new)
    fresh = s["author"]()
    fresh.step()
    fresh.step()
    out = [
        o for m in hub.messages if (o := decode(m.body)) and o["t"] in ("withheld", "disclosure")
    ]
    assert [(o["t"], o.get("reason")) for o in out] == [("withheld", "session_changed")]
    assert types(hub).count("seal") == 1


def _rerequest(hub: FakeSwitch, ra: str, q: int) -> None:
    """reviewer-agent asks for the same leaves again, under question ``q``."""
    req = next(m for m in hub.messages if (o := decode(m.body)) and o["t"] == "request")
    body = req.body.replace("Q1 ·", f"Q{q} ·").replace('"q":1', f'"q":{q}')
    FakeTransport(hub, ra).post("pr", body)


def _decided(hub: FakeSwitch, t: str) -> list[tuple[int, int]]:
    return sorted((o["q"], o["i"]) for m in hub.messages if (o := decode(m.body)) and o["t"] == t)


def test_one_card_per_leaf_and_its_answer_covers_every_question(tmp_path: Path) -> None:
    # Found on a real PR: one merged step edited three files, so two SCOPE questions
    # requested the same leaves and the author got a card per question for the same bytes.
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    hub = s["hub"]
    a, r = s["author"](), s["reviewer"]()
    a.step()
    r.step()
    _rerequest(hub, s["ra"], 2)
    a.step()
    leaves = {
        i
        for m in hub.messages
        if (o := decode(m.body)) and o["t"] == "request"
        for i in o["leaves"]
    }
    assert len(hub.cards) == len(leaves)
    for card in list(hub.cards):
        hub.answer(s["au"], card, "approve")
    a.step()
    assert _decided(hub, "disclosure") == sorted((q, i) for q in (1, 2) for i in leaves)
    _rerequest(hub, s["ra"], 3)
    a = s["author"]()  # restart: the decision is read back from the room
    a.step()
    assert len(hub.cards) == len(leaves)
    assert {q for q, _ in _decided(hub, "disclosure")} == {1, 2, 3}


def test_declined_leaf_is_withheld_for_every_question(tmp_path: Path) -> None:
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    hub = s["hub"]
    a, r = s["author"](), s["reviewer"]()
    a.step()
    r.step()
    _rerequest(hub, s["ra"], 2)
    a.step()
    for card in list(hub.cards):
        hub.answer(s["au"], card, "decline")
    a.step()
    withheld = [o for m in hub.messages if (o := decode(m.body)) and o["t"] == "withheld"]
    assert sorted({w["q"] for w in withheld}) == [1, 2]
    assert {w["reason"] for w in withheld} == {"author"}
    assert _decided(hub, "disclosure") == []


def test_state_from_another_room_is_not_reused(tmp_path: Path) -> None:
    # Found live: an author repo whose .git/flipside/work-author came from an earlier run
    # (same sealed commit, other rooms) believed its 8 cards were already open, so the new
    # room never got a card and the flow stalled after the request.
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    a, r = s["author"](), s["reviewer"]()
    a.step()
    r.step()
    a.step()
    assert len(s["hub"].cards) == 1
    s2 = setup(world, tmp_path, Clock(), rooms=("pr-second", "priv-second"))
    a, r = s2["author"](), s2["reviewer"]()
    a.step()
    r.step()
    a.step()
    assert len(s2["hub"].cards) == 1


SLACK_PRIYA = "@switch-slack-b1-priya"


def press_in_slack(hub: FakeSwitch, who: str) -> None:
    """Switch reports a card answered from Slack under the presser's bridged identity."""
    card = hub.cards[next(iter(hub.cards))]
    card.answer, card.answered_by = "approve", who


def test_a_card_pressed_in_slack_by_the_author_is_honoured(tmp_path: Path) -> None:
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock(), answerers=(SLACK_PRIYA,))
    hub, a, r = s["hub"], s["author"](), s["reviewer"]()
    a.step()
    r.step()
    a.step()
    press_in_slack(hub, SLACK_PRIYA + ":localhost")
    a.step()
    assert "disclosure" in types(hub)


def test_a_slack_press_by_anyone_else_is_ignored(tmp_path: Path) -> None:
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock(), answerers=(SLACK_PRIYA,))
    hub, a, r = s["hub"], s["author"](), s["reviewer"]()
    a.step()
    r.step()
    a.step()
    press_in_slack(hub, "@switch-slack-b1-omar:localhost")
    a.step()
    assert "disclosure" not in types(hub)


def test_only_the_whole_local_part_of_a_slack_id_matches() -> None:
    cfg_ok = AuthorConfig(
        1, "pr", "priv", Path("."), "", "", "ra", "a", "priya", author_answerers=(SLACK_PRIYA,)
    )
    assert cfg_ok.answered_by_author("a")
    assert cfg_ok.answered_by_author(SLACK_PRIYA + ":localhost")
    assert not cfg_ok.answered_by_author(SLACK_PRIYA + "x:localhost")
    assert not cfg_ok.answered_by_author("user:" + SLACK_PRIYA)
    assert not cfg_ok.answered_by_author("@switch-slack-b1-omar:localhost")


def test_the_questions_line_says_each_question_in_words(tmp_path: Path) -> None:
    """The author reads the question in the room's human line, not in the JSON (issue #65)."""
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    s["author"]().step()
    s["reviewer"]().step()
    msgs = s["hub"].messages
    body = next(m.body for m in msgs if (o := decode(m.body)) and o["t"] == "questions")
    line, q1 = body.split("\n", 1)[0], decode(body)["qs"][0]  # type: ignore[index]
    assert f"Q1 {q1['text']}" in line
    assert line.endswith("answer each as Q<k>: in your own words")


def _stale_verdicts(hub: FakeSwitch, ra: str, commit: str) -> None:
    """reviewer-agent's OK verdicts for every requested leaf, from an earlier seal (``commit``)
    in the same room, as a room reused after a re-seal holds them."""
    req = next(o for m in hub.messages if (o := decode(m.body)) and o["t"] == "request")
    for i in req["leaves"]:
        obj = {"t": "verdict", "v": 1, "commit": commit, "i": i, "q": req["q"], "code": "OK"}
        FakeTransport(hub, ra).post(
            "pr", encode(f"Q{req['q']} · leaf {i} · OK (earlier seal)", obj)
        )


def test_verdicts_from_an_earlier_seal_do_not_settle_this_round(tmp_path: Path) -> None:
    # Every other piece of round state (questions, requests, withheld, brief) is read for the
    # round's seal commit only; verdicts were read for any commit, so an OK verdict left in a
    # reused room by an earlier seal made the brief go out before this seal's leaf was checked.
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    hub = s["hub"]
    a, r = s["author"](), s["reviewer"]()
    a.step()
    r.step()
    _stale_verdicts(hub, s["ra"], "f" * 40)
    hub.post(s["au"], "pr", "Q1: the export test needed a longer session")
    r.step()
    assert "brief" not in types(hub)
    a.step()
    hub.answer(s["au"], next(iter(hub.cards)), "approve")
    a.step()
    r.step()
    brief = next(o for m in hub.messages if (o := decode(m.body)) and o["t"] == "brief")
    assert types(hub).count("verdict") == 1 + len(_decided(hub, "disclosure"))
    assert brief["commit"] == world.commit


def test_a_plain_answer_from_before_this_rounds_questions_does_not_count(tmp_path: Path) -> None:
    # Relayed answers carry the seal commit; a plain `Q<k>:` answer has none, so it was counted
    # for any round. In a room reused after a re-seal, the author's answer to the earlier
    # round's Q1 then answered this round's Q1, about different code.
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    hub = s["hub"]
    a, r = s["author"](), s["reviewer"]()
    a.step()
    hub.post(s["au"], "pr", "Q1: stale answer to the earlier seal's question")
    r.step()
    a.step()
    hub.answer(s["au"], next(iter(hub.cards)), "approve")
    a.step()
    r.step()
    assert "brief" not in types(hub)
    hub.post(s["au"], "pr", "Q1: the export test needed a longer session")
    r.step()
    brief = next(m.body for m in hub.messages if (o := decode(m.body)) and o["t"] == "brief")
    assert "longer session" in brief
    assert "stale answer" not in brief
