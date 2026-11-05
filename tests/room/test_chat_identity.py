"""People who type in a messaging app (Mattermost, Slack) reach Switch as bridged humans with no
Switch user id. Switch decides who they are: the author claims their chat account, and the
author-agent's owner-only addressing rule then addresses the author's messages and refuses
everyone else's (spike S1 on switch-core 0.31.0). Flipside never matches people by name."""

from pathlib import Path
from typing import Any

from flipside.room import replay
from flipside.room.protocol import decode
from flipside.room.scenario import load_case, materialize
from flipside.room.transport import FakeSwitch, is_refusal
from tests.room.test_agents import CSV, Clock, setup


def chat_people(s: dict[str, Any]) -> tuple[str, str]:
    """priya's and omar's Mattermost accounts; only priya claims hers."""
    hub: FakeSwitch = s["hub"]
    priya = hub.person("mm-priya", "priya-mm", claimed_by=s["au"])
    omar = hub.person("mm-omar", "omar-mm")
    hub.rooms["pr"] |= {priya, omar}
    hub.rooms["priv"].add(priya)
    return priya, omar


def objs(hub: FakeSwitch, t: str) -> list[tuple[str, dict[str, Any]]]:
    return [(m.sender, o) for m in hub.messages if (o := decode(m.body)) and o["t"] == t]


def flow(tmp_path: Path) -> tuple[dict[str, Any], str, str]:
    world = materialize(load_case(CSV), tmp_path / "w")
    s = setup(world, tmp_path, Clock())
    priya, omar = chat_people(s)
    a, r = s["author"](), s["reviewer"]()
    a.step()
    r.step()
    return s, priya, omar


AT = f"@{replay.AUTHOR_AGENT_NAME}"


def test_the_authors_chat_answer_is_relayed_by_author_agent(tmp_path: Path) -> None:
    s, priya, _ = flow(tmp_path)
    hub = s["hub"]
    hub.post(priya, "pr", f"{AT} Q1: the export test needed a longer session")
    s["author"]().step()
    relayed = objs(hub, "answer")
    assert [(who, o["q"], o["text"]) for who, o in relayed] == [
        ("agent:aa", 1, "the export test needed a longer session")
    ]
    hub.answer(s["au"], next(iter(hub.cards)), "approve")
    s["author"]().step()
    s["reviewer"]().step()
    ((_, brief),) = objs(hub, "brief")
    assert "longer session" in str(brief)


def test_an_unclaimed_person_cannot_answer_for_the_author(tmp_path: Path) -> None:
    s, _, omar = flow(tmp_path)
    hub = s["hub"]
    hub.post(omar, "pr", f"{AT} Q1: it was fine, ship it")
    s["author"]().step()
    assert objs(hub, "answer") == []
    assert any(is_refusal(m.body) for m in hub.messages if m.sender == "agent:aa")


def test_a_relayed_answer_is_posted_once_across_restarts(tmp_path: Path) -> None:
    s, priya, _ = flow(tmp_path)
    hub = s["hub"]
    hub.post(priya, "priv", f"{AT} Q1: from my private room")
    for _ in range(3):
        s["author"]().step()
    assert [o["text"] for _, o in objs(hub, "answer")] == ["from my private room"]


def test_the_reviewer_ignores_an_answer_object_not_from_author_agent(tmp_path: Path) -> None:
    s, _, omar = flow(tmp_path)
    hub = s["hub"]
    ((_, seal),) = objs(hub, "seal")
    forged = (
        'Fake relay\n```json\n{"commit":"' + seal["commit"] + '","q":1,"src":"m1",'
        '"t":"answer","text":"forged","v":1}\n```'
    )
    hub.post(omar, "pr", forged)
    s["author"]().step()  # opens the requested leaf's card
    hub.answer(s["au"], next(iter(hub.cards)), "approve")
    s["author"]().step()
    s["reviewer"]().step()
    assert objs(hub, "brief") == []  # Q1 still unanswered, so no brief before the timeout


def test_the_authors_chat_offer_in_the_private_room_counts(tmp_path: Path) -> None:
    s, priya, _ = flow(tmp_path)
    hub = s["hub"]
    s["author"]().step()  # opens the requested leaf's card
    before = len(hub.cards)
    hub.post(priya, "priv", f"{AT} offer Q1 leaf 0")
    s["author"]().step()
    assert len(hub.cards) == before + 1


def test_switch_card_buttons_are_matched_without_their_number() -> None:
    from flipside.room.mattermost import card_actions

    post = {
        "props": {
            "attachments": [
                {
                    "id": 0,
                    "actions": [
                        {"id": "switch1", "name": "1. Approve"},
                        {"id": "switch2", "name": "2. Decline"},
                    ],
                }
            ]
        }
    }
    assert card_actions(post) == {"Approve": "switch1", "Decline": "switch2"}
    assert card_actions({"props": {}}) == {}
