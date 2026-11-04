from dataclasses import replace
from pathlib import Path

import pytest

from ownership_gate import live as live_module
from ownership_gate.gate import Status
from ownership_gate.live import LiveConfig, LiveGate, _room_id
from ownership_gate.model import CheckRun
from ownership_gate.switch_client import ChatMessage, SwitchError
from tests.test_controller import PR, SESSION


class FakeAgent:
    def __init__(self, fail_posts=0, room_result=None):
        self.posts = []
        self.fail_posts = fail_posts
        self.room_result = {"room_id": "room-new"} if room_result is None else room_result

    def post(self, room_id, body, thread_id=None):
        if self.fail_posts:
            self.fail_posts -= 1
            raise SwitchError("down")
        self.posts.append((room_id, body, thread_id))

    def create_room(self, yaml_text, inputs):
        return self.room_result


def gate(tmp_path: Path) -> LiveGate:
    config = LiveConfig(
        repo="acme/shop",
        author="dana",
        chat_user="dana.k",
        repo_dir=tmp_path,
        agent_name="dana-gate",
        reviewer_chat="sam",
        state_dir=tmp_path / ".ogate",
    )
    live = LiveGate(config=config, agent=FakeAgent())
    live.rooms[PR.key] = "room-1"
    live.controller.open(PR, SESSION)
    return live


def msg(sender: str, body: str, room: str = "room-1") -> ChatMessage:
    return ChatMessage(room, "m1", "@u", sender, body, "t1", True)


def test_answers_from_the_authors_chat_account_reach_the_gate(tmp_path):
    live = gate(tmp_path)

    live.handle(msg("dana.k", "1: I tested the migration."))

    room, body, thread = live.agent.posts[0]
    assert (room, thread) == ("room-1", "t1")
    assert "Contradiction in answer 1" in body
    assert "@dana.k, revise" in body


def test_other_senders_and_rooms_are_ignored(tmp_path):
    live = gate(tmp_path)

    live.handle(msg("sam", "1: fine"))
    live.handle(msg("dana.k", "1: fine", room="other-room"))

    assert live.agent.posts == []


def fresh_gate(tmp_path: Path, agent: FakeAgent) -> LiveGate:
    live = gate(tmp_path)
    live.agent = agent
    live.rooms.clear()
    live.controller.forget(PR.key)
    return live


def test_open_gate_creates_the_room_then_posts_the_opening(tmp_path):
    live = fresh_gate(tmp_path, FakeAgent())

    live.open_gate(PR)

    assert live.rooms[PR.key] == "room-new"
    assert live.agent.posts[0][0] == "room-new"
    assert "Ownership Gate for" in live.agent.posts[0][1]
    assert live.controller.is_current(PR)


def test_failed_opening_post_is_retried_on_the_next_poll(tmp_path):
    live = fresh_gate(tmp_path, FakeAgent(fail_posts=1))

    live.open_gate(PR)

    assert not live.controller.is_current(PR)

    live.open_gate(PR)

    assert live.controller.is_current(PR)
    assert len([p for p in live.agent.posts if "Ownership Gate for" in p[1]]) == 1


def test_room_creation_failure_leaves_no_gate(tmp_path):
    live = fresh_gate(tmp_path, FakeAgent(room_result={"error": "nope"}))

    with pytest.raises(SwitchError):
        live.open_gate(PR)

    assert not live.controller.is_current(PR)
    assert PR.key not in live.rooms


@pytest.mark.parametrize("checks", [(), (CheckRun("ci", None),)])
def test_gate_waits_for_ci_until_the_grace_period_ends(tmp_path, checks):
    live = fresh_gate(tmp_path, FakeAgent())
    now = [0.0]
    live.clock = lambda: now[0]
    pending = replace(PR, checks=checks)

    live.open_gate(pending)
    now[0] = live.config.ci_grace_seconds - 1
    live.open_gate(pending)

    assert live.agent.posts == []

    now[0] = live.config.ci_grace_seconds
    live.open_gate(pending)

    assert live.controller.is_current(pending)


def test_room_id_is_found_in_nested_results():
    assert _room_id({"room_id": "r1", "room_name": "x"}) == "r1"
    assert _room_id({"rooms": [{"id": "r2"}]}) == "r2"
    assert _room_id({"nothing": 1}) == ""


def test_failed_reply_and_everything_after_it_wait_in_order(tmp_path):
    live = gate(tmp_path)
    live.agent.fail_posts = 1

    live.handle(msg("dana.k", "1: I tested the migration.\n2: auth needs the user."))

    assert live.agent.posts == []
    assert len(live.outbox) >= 1

    queued = [o.text for o in live.outbox]
    live.flush_outbox()

    assert [p[1] for p in live.agent.posts] == queued
    assert live.outbox == []
    assert "Contradiction in answer 1" in live.agent.posts[0][1]


def test_restart_rebuilds_the_gate_from_the_log_without_posting(tmp_path, monkeypatch):
    monkeypatch.setattr(live_module, "load_session", lambda repo_dir, ids: SESSION)
    first = fresh_gate(tmp_path, FakeAgent())
    first.open_gate(PR)
    first.handle(msg("dana.k", "1: I tested the migration.", room="room-new"))

    restarted = LiveGate(config=first.config, agent=FakeAgent())
    restarted.open_gate(PR)

    assert restarted.agent.posts == []
    assert restarted.controller.is_current(PR)
    assert restarted.controller.status(PR.key) is first.controller.status(PR.key)
    assert restarted.controller.status(PR.key) is Status.CONTRADICTED
    assert restarted.controller.gates[PR.key].latest(1) is not None


class InviteFails(FakeAgent):
    def op(self, name, args):
        raise SwitchError("invite refused")


def test_invite_failure_keeps_the_room_so_no_duplicate_is_made(tmp_path):
    live = fresh_gate(tmp_path, InviteFails())
    live.config.reviewer_agent = "sam-review"

    live.open_gate(PR)

    assert live.rooms[PR.key] == "room-new"
    assert live.controller.is_current(PR)
