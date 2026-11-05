"""Rooms bridged to a messaging app (Slack) for `flip solo --slack`: room creation, the
creator's membership, inviting the people's linked accounts, and picking the connection."""

from __future__ import annotations

from typing import Any

import pytest

from flipside.room import setup
from flipside.room.switch_client import Http


class Recorder(Http):
    """Records calls; answers the few reads the bridge helpers make."""

    def __init__(self, me: str = "u-me", identities: list[dict[str, Any]] | None = None) -> None:
        super().__init__("http://fake")
        self.calls: list[tuple[str, str, Any]] = []
        self.me = me
        self.identities = identities or []
        self.bridges: list[dict[str, Any]] = []

    def get(self, path: str) -> Any:
        self.calls.append(("GET", path, None))
        if path == "/gateway/auth/me":
            return {"id": self.me}
        if path == "/gateway/auth/me/identities":
            return self.identities
        if path == "/gateway/collaborations":
            return self.bridges
        return {}

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self.calls.append(("POST", path, body))
        if path == "/gateway/chats":
            return {"chat": {"roomId": "chat-1"}}
        if path == "/gateway/rooms":
            return {"id": "room-1"}
        return {}


def test_without_a_bridge_the_room_is_a_switch_chat_with_its_greeting() -> None:
    h = Recorder()
    assert setup.open_room(h, "pr-7", "agent-r", "hello") == "chat-1"
    [(method, path, body)] = h.calls
    assert (method, path) == ("POST", "/gateway/chats")
    assert body["agentIds"] == ["agent-r"] and body["greeting"] == "hello"


def test_a_bridged_room_is_a_private_channel_and_its_creator_joins_it() -> None:
    h = Recorder(me="u-rev")
    assert setup.open_room(h, "pr-7", "agent-r", "hello", bridge="b-1") == "room-1"
    posts = [(p, b) for m, p, b in h.calls if m == "POST"]
    assert posts[0] == (
        "/gateway/rooms",
        {
            "name": "pr-7",
            "description": "hello",
            "agent_ids": ["agent-r"],
            "bridge_id": "b-1",
            "channel_type": "channel_private",
            "read_visibility": "private",
            "write_visibility": "private",
        },
    )
    # Without this the creator's gateway reads of the room return 403 NOT_A_MEMBER.
    assert posts[1] == ("/gateway/chats/room-1/members", {"userId": "u-rev"})


def test_linked_names_are_only_the_ones_on_this_bridge() -> None:
    h = Recorder(
        identities=[
            {"bridge_id": "b-1", "external_username": "priya"},
            {"bridge_id": "b-2", "external_username": "priya-other"},
        ]
    )
    assert setup.linked_names(h, "b-1") == ["priya"]


def test_invite_posts_the_names_and_skips_an_empty_list() -> None:
    h = Recorder()
    setup.invite(h, "room-1", ["priya", "omar"])
    setup.invite(h, "room-1", [])
    assert h.calls == [("POST", "/gateway/rooms/room-1/users", {"user_names": ["priya", "omar"]})]


def test_slack_bridge_prefers_the_active_default_connection() -> None:
    h = Recorder()
    h.bridges = [
        {"bridge_id": "b-off", "bridge_type": "slack", "status": "error", "is_default": True},
        {"bridge_id": "b-2", "bridge_type": "slack", "status": "active", "is_default": False},
        {"bridge_id": "b-1", "bridge_type": "slack", "status": "active", "is_default": True},
        {"bridge_id": "b-d", "bridge_type": "discord", "status": "active", "is_default": True},
    ]
    assert setup.slack_bridge(h) == "b-1"


def test_slack_bridge_without_a_connection_says_how_to_add_one() -> None:
    with pytest.raises(setup.SetupError, match="Messaging apps"):
        setup.slack_bridge(Recorder())


def test_bridged_ids_are_the_ids_switch_reports_for_a_slack_press() -> None:
    # Seen live in K3: answeredBy "@switch-slack-<connection>-<username>:localhost".
    h = Recorder(identities=[{"bridge_id": "b-1", "external_username": "priya"}])
    assert setup.bridged_ids(h, "b-1") == ["@switch-slack-b-1-priya"]


def test_a_bridged_room_is_private_to_its_creator() -> None:
    """Switch 0.31.0 makes a room created through /gateway/rooms public to the workspace
    unless asked otherwise, so the reviewer could rename the author's private room or rewrite
    its instructions without being in it (spike S5). A chat is private by default."""
    h = Recorder()
    setup.open_room(h, "pr-7-author", "agent-a", "hello", bridge="b-1")
    [body] = [b for m, p, b in h.calls if (m, p) == ("POST", "/gateway/rooms")]
    assert body["read_visibility"] == "private" and body["write_visibility"] == "private"
