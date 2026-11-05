"""The author's Approve press must reach Switch before the run moves on.

Found in CI on 5 Nov 2026 (21:07 IST, widened-cors on Ubuntu): the author pressed Approve in the
same second the card appeared, Mattermost answered OK, Switch never recorded the answer, and the
run waited 60 s with no disclosure.
"""

from __future__ import annotations

from typing import Any

import pytest

from flipside.room.mattermost import MattermostError, MattermostHumans

CARD = "e4f30fb0-0000-0000-0000-000000000000"
TITLE = "Disclose step 5 chunk 0 to #pr-144?"


class FakeMM:
    """The author's Mattermost: one card post with Approve and Decline."""

    def __init__(self) -> None:
        self.presses: list[str] = []

    def call(self, method: str, path: str, body: Any = None) -> Any:
        if method == "GET":
            post = {
                "message": "",
                "props": {
                    "attachments": [
                        {
                            "title": TITLE,
                            "actions": [
                                {"id": "a1", "name": "1. Approve"},
                                {"id": "a2", "name": "2. Decline"},
                            ],
                        }
                    ]
                },
            }
            return {"order": ["p1"], "posts": {"p1": post}}
        self.presses.append(path)
        return {"status": "OK"}


class FakeGateway:
    """Switch's approvals list: the card stays open until press number ``lands_on``."""

    def __init__(self, mm: FakeMM, lands_on: int | None) -> None:
        self.mm = mm
        self.lands_on = lands_on

    def get(self, path: str) -> list[dict[str, Any]]:
        answered = self.lands_on is not None and len(self.mm.presses) >= self.lands_on
        state = "approved" if answered else "open"
        row = {"requestId": CARD, "roomId": "priv", "state": state}
        return [{**row, "agentId": "ag", "sessionId": "s", "title": TITLE}]


def humans(lands_on: int | None) -> tuple[MattermostHumans, FakeMM, list[str]]:
    mm = FakeMM()
    logs: list[str] = []
    h = MattermostHumans(
        people={"author": mm},  # type: ignore[dict-item]
        channels={"priv": "chan"},
        gateway={"author": FakeGateway(mm, lands_on)},  # type: ignore[dict-item]
        agents={},
        private="priv",
        log=logs.append,
        press_wait=1.0,
        confirm_wait=0.2,
    )
    h.seen[CARD] = ("ag", "s", TITLE)
    return h, mm, logs


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("flipside.room.mattermost.time.sleep", lambda s: None)


def test_one_press_when_switch_records_it() -> None:
    h, mm, _ = humans(lands_on=1)
    h.answer_card("author", CARD, "approve")
    assert mm.presses == ["/posts/p1/actions/a1"]


def test_presses_again_when_the_first_press_does_not_reach_switch() -> None:
    h, mm, logs = humans(lands_on=2)
    h.answer_card("author", CARD, "approve")
    assert len(mm.presses) == 2
    assert any("did not reach Switch" in line for line in logs)


def test_gives_up_with_an_error_after_three_lost_presses() -> None:
    h, mm, _ = humans(lands_on=None)
    with pytest.raises(MattermostError, match="never reached Switch"):
        h.answer_card("author", CARD, "approve")
    assert len(mm.presses) == 3
