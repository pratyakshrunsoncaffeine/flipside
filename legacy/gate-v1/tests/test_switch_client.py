import json

from ownership_gate.switch_client import SwitchAgent, parse_frames, parse_sse, to_message


def test_parses_multi_line_events_and_skips_comments():
    lines = [
        ": keep-alive\n",
        'data: {"type": "connection_state",\n',
        'data:  "x": 1}\n',
        "\n",
        "data: not json\n",
        "\n",
        f"data: {json.dumps({'type': 'message', 'room_id': 'r1', 'payload': {'body': 'hi'}})}\n",
        "\n",
    ]

    events = list(parse_sse(lines))

    assert [e["type"] for e in events] == ["connection_state", "message"]


def test_maps_a_message_event():
    event = {
        "type": "message",
        "room_id": "r1",
        "payload": {
            "message_id": "m1",
            "sender": "@switch-user-1:local",
            "sender_name": "dana",
            "body": "1: answer",
            "thread_id": "t1",
            "addressed": True,
        },
    }

    message = to_message(event)

    assert message is not None
    assert (message.room_id, message.sender_name, message.thread_id) == ("r1", "dana", "t1")
    assert message.addressed


def test_ignores_non_message_events():
    assert to_message({"type": "connection_state"}) is None


def test_frames_carry_their_id_and_event_name():
    lines = [
        "id: 41\n",
        "event: message\n",
        'data: {"type": "message"}\n',
        "\n",
        "event: evicted\n",
        'data: {"code": "heartbeat_lapsed"}\n',
        "\n",
    ]

    frames = list(parse_frames(lines))

    assert [(f.id, f.event) for f in frames] == [("41", "message"), (None, "evicted")]


class RecordingAgent(SwitchAgent):
    def op(self, name, args):
        self.calls.append((name, args.get("room_id") or args.get("body")))


def test_post_reconnects_whenever_the_room_changes():
    agent = RecordingAgent("http://x", "a1", "k")
    agent.calls = []

    agent.post("r1", "one")
    agent.post("r1", "two")
    agent.post("r2", "three")
    agent.post("r1", "four")

    assert agent.calls == [
        ("connect_to_room", "r1"),
        ("post_message", "one"),
        ("post_message", "two"),
        ("connect_to_room", "r2"),
        ("post_message", "three"),
        ("connect_to_room", "r1"),
        ("post_message", "four"),
    ]
