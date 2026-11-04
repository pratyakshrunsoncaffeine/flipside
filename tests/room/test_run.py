"""The duplicate-post check behind the M3 restart test."""

from typing import Any

from flipside.room.protocol import encode
from flipside.room.run import duplicates


def row(mid: str, sender: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {"id": mid, "seq": 0, "sender": sender, "body": encode("x", {"v": 1, **obj})}


def test_a_repeated_post_is_a_duplicate() -> None:
    rows = [
        row("m1", "author-agent", {"t": "seal", "commit": "c" * 40}),
        row("m2", "reviewer-agent", {"t": "request", "commit": "c" * 40, "q": 1}),
        row("m3", "author-agent", {"t": "seal", "commit": "c" * 40}),
        row("m4", "reviewer-agent", {"t": "request", "commit": "c" * 40, "q": 1}),
    ]
    assert duplicates(rows) == ["m3", "m4"]


def test_distinct_posts_and_attack_posts_are_not_duplicates() -> None:
    rows = [
        row("m1", "reviewer-agent", {"t": "request", "commit": "c" * 40, "q": 1}),
        row("m2", "reviewer-agent", {"t": "request", "commit": "c" * 40, "q": 2}),
        row("m3", "reviewer-agent", {"t": "verdict", "ref": "d1"}),
        row("m4", "reviewer-agent", {"t": "verdict", "ref": "d2"}),
        row("m5", "reviewer-agent", {"t": "request", "commit": "c" * 40, "q": 1}),
    ]
    assert duplicates(rows) == ["m5"]
    assert duplicates(rows, frozenset({"m5"})) == []


def test_plain_chat_lines_are_ignored() -> None:
    rows = [{"id": f"m{k}", "seq": k, "sender": "user", "body": "Q1: same"} for k in range(3)]
    assert duplicates(rows) == []


def test_verdicts_are_counted_in_the_room_including_after_the_brief() -> None:
    from flipside.room.run import Refusals, Result

    def r(mid: str, sender: str, obj: dict[str, Any]) -> dict[str, Any]:
        return {**row(mid, sender, obj), "sender_id": sender}

    rows = [
        r("m1", "agent:rev", {"t": "verdict", "ref": "d1", "code": "OK"}),
        r("m2", "agent:rev", {"t": "brief", "commit": "c" * 40}),
        r("m3", "agent:rev", {"t": "verdict", "ref": "d2", "code": "PROOF_FAIL"}),
        r("m4", "agent:author", {"t": "verdict", "ref": "d3", "code": "OK"}),
    ]
    res = Result(rows, {"gaps": []}, Refusals(), 1, reviewer_id="agent:rev")
    assert res.summary()["verdicts"] == {"OK": 1, "PROOF_FAIL": 1}
