"""`SwitchAgent.messages()` against a local SSE server that behaves like Switch's."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from ownership_gate.switch_client import SwitchAgent, SwitchError


def sse(event: str, data: dict, event_id: str | None = None) -> bytes:
    head = f"id: {event_id}\n" if event_id else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def message(room: str, body: str) -> dict:
    return {"type": "message", "room_id": room, "payload": {"sender_name": "dana", "body": body}}


class FakeSwitch(BaseHTTPRequestHandler):
    frames: ClassVar[list[bytes]] = []
    seen_last_event_ids: ClassVar[list[str | None]] = []
    beat_status = 200

    def do_GET(self):
        FakeSwitch.seen_last_event_ids.append(self.headers.get("Last-Event-ID"))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for frame in FakeSwitch.frames:
            self.wfile.write(frame)
            self.wfile.flush()

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(FakeSwitch.beat_status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    FakeSwitch.frames, FakeSwitch.seen_last_event_ids = [], []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeSwitch)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_resumes_after_the_last_event_id(server):
    FakeSwitch.frames = [sse("message", message("r1", "1: hi"), "41")]
    agent = SwitchAgent(server, "a1", "k")

    first = [m.body for m in agent.messages()]
    list(agent.messages())

    assert first == ["1: hi"]
    assert FakeSwitch.seen_last_event_ids == [None, "41"]


def test_eviction_ends_the_stream_with_a_fresh_connection_id(server):
    FakeSwitch.frames = [sse("evicted", {"code": "taken_over"})]
    agent = SwitchAgent(server, "a1", "k")
    old = agent.connection_id

    with pytest.raises(SwitchError, match="evicted"):
        list(agent.messages())

    assert agent.connection_id != old


def test_a_stream_forgets_the_connected_room(server):
    FakeSwitch.frames = [sse("message", message("r1", "x"), "1")]
    agent = SwitchAgent(server, "a1", "k")
    agent._room = "r1"

    list(agent.messages())

    assert agent._room is None
