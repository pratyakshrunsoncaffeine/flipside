"""`flip solo --slack --press`: the people's script leaves the author's card for the author
to answer in their own client, and the flow finishes once they do."""

from __future__ import annotations

from pathlib import Path

from flipside.room import replay
from flipside.room.protocol import decode
from flipside.room.replay import FakeHumans
from flipside.room.run import Cast, Script, play
from flipside.room.scenario import load_case, materialize
from flipside.room.transport import FakeSwitch, FakeTransport, Rule

CSV = Path(__file__).resolve().parents[2] / "fixtures" / "cases" / "csv-export"


def test_by_hand_waits_for_the_author_and_finishes_after_their_answer(tmp_path: Path) -> None:
    world = materialize(load_case(CSV), tmp_path / "w")
    hub = FakeSwitch()
    au, ru = hub.user("u-a", "priya"), hub.user("u-r", "omar")
    aa = hub.agent("a-a", replay.AUTHOR_AGENT_NAME, au)
    ra = hub.agent("a-r", replay.REVIEWER_AGENT_NAME, ru)
    shared = hub.room("pr-142", [au, ru, aa, ra])
    private = hub.room("pr-142-author", [au, aa])
    hub.set_policy(aa, [Rule(owner=True), Rule(agents=(ra,), rooms=(shared,))], by=au)
    cast = Cast(au, ru, aa, ra, shared, private, "priya", "omar")
    at, rt = FakeTransport(hub, aa), FakeTransport(hub, ra)
    author = replay.author_agent(world, at, cast, tmp_path, lambda _m: None)
    reviewer = replay.reviewer_agent(world, rt, cast, lambda _m: None, replay.FakeClock())
    script = Script(
        world,
        FakeHumans(hub, {"author": au, "reviewer": ru}),
        cast,
        at,
        rt,
        replay.AUTHOR_AGENT_NAME,
        lambda _m: None,
    )
    script.by_hand = True

    def run(rounds: int) -> list[str]:
        play(
            world,
            script,
            lambda: hub.read(au, shared),
            lambda _m: None,
            author_step=author.step,
            reviewer_step=reviewer.step,
            max_rounds=rounds,
        )
        return [o["t"] for m in hub.messages if (o := decode(m.body))]

    before = run(12)
    assert "disclosure" not in before and "brief" not in before
    [(card, _)] = hub.pending(au)
    assert len(script.refusals.card_403) == 1  # the reviewer's attempt still runs

    hub.answer(au, card, "approve")  # the author presses Approve in their client
    after = run(12)
    assert "disclosure" in after and "brief" in after
