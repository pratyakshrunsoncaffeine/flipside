"""Minimal Switch custom-agent client: register, stream events, beat, call operations.

Follows Switch v0.9's own Python harness (core/tests/e2e/follow_the_conversation/
harness.py): `POST /agents` to register, SSE on `/agents/{id}/events`, a heartbeat on
`/connection/beat`, and `POST /agents/{id}/ops/{name}` with `X-Switch-Connection-Id`.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

BEAT_SECONDS = 2.0
BEAT_MISSES_ALLOWED = 3
# Three missed 15 s server keepalives mean the TCP connection is dead.
STREAM_TIMEOUT_SECONDS = 45.0
# A beat answered 404 or 409 means the server dropped this connection: reopen the stream.
CONNECTION_GONE = frozenset({404, 409})


class SwitchError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class SseFrame:
    """One server-sent event. `id` is what a reconnect sends back as `Last-Event-ID`."""

    id: str | None
    event: str
    data: Any


@dataclass(frozen=True)
class ChatMessage:
    room_id: str
    message_id: str
    sender: str
    sender_name: str
    body: str
    thread_id: str | None
    addressed: bool


def register(base_url: str, token: str, name: str, description: str) -> dict[str, str]:
    """Register (or overwrite) a custom always-on agent; returns `{id, api_key}`.

    `token` is a registration token or the owner's personal API key. Use the personal
    key so the agent is owned by, and addressable only by, the PR author.
    """
    body = {
        "name": name,
        "description": description,
        "connector_type": "custom",
        "overwrite": True,
        "integration_profile": {
            "connection_model": "always_on",
            "message_exchange": True,
            "pre_invocation_mediation": [],
            "post_invocation_mediation": [],
            "event_reporting": [],
        },
    }
    return _post(f"{base_url}/agents", token, body)


def parse_sse(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    """Yield the JSON object of each SSE event; ignores comments and keep-alives."""
    for frame in parse_frames(lines):
        if isinstance(frame.data, dict):
            yield frame.data


def parse_frames(lines: Iterable[str]) -> Iterator[SseFrame]:
    """Yield each SSE event with its id and name; skips comments and unparsable data."""
    data: list[str] = []
    event_id: str | None = None
    name = "message"
    for raw in lines:
        line = raw.rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].strip())
        elif line.startswith("id:"):
            event_id = line[3:].strip()
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif not line:
            parsed = _json_or_none("\n".join(data)) if data else None
            if parsed is not None:
                yield SseFrame(event_id, name, parsed)
            data, event_id, name = [], None, "message"


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def to_message(event: dict[str, Any]) -> ChatMessage | None:
    if event.get("type") != "message":
        return None
    p = event.get("payload") or {}
    return ChatMessage(
        room_id=str(event.get("room_id", "")),
        message_id=str(p.get("message_id", "")),
        sender=str(p.get("sender", "")),
        sender_name=str(p.get("sender_name") or ""),
        body=str(p.get("body") or ""),
        thread_id=p.get("thread_id"),
        addressed=bool(p.get("addressed")),
    )


@dataclass
class SwitchAgent:
    base_url: str
    agent_id: str
    api_key: str
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_event_id: str | None = None
    _room: str | None = None
    _post_lock: threading.Lock = field(default_factory=threading.Lock)

    def op(self, name: str, args: dict[str, Any]) -> Any:
        url = f"{self.base_url}/agents/{self.agent_id}/ops/{name}"
        headers = {"X-Switch-Connection-Id": self.connection_id}
        return _post(url, self.api_key, args, headers).get("result")

    def post(self, room_id: str, body: str, thread_id: str | None = None) -> Any:
        """Post into `room_id`. `post_message` goes to the connection's current room, so
        connecting and posting happen under one lock and a post never lands elsewhere."""
        with self._post_lock:
            if self._room != room_id:
                self._room = None
                args = {"room_id": room_id, "include_general_instructions": False}
                self.op("connect_to_room", args)
                self._room = room_id
            return self.op("post_message", {"body": body, "thread_id": thread_id})

    def create_room(self, yaml_text: str, inputs: dict[str, Any]) -> Any:
        with self._post_lock:
            self._room = None
            return self.op("create_room_from_yaml", {"yaml": yaml_text, "inputs": inputs})

    def messages(self) -> Iterator[ChatMessage]:
        """Stream chat messages until the connection drops. Beats in the background.

        A reopened stream resumes after `last_event_id`, so a drop loses no messages
        while the server still holds them. An `evicted` frame ends the stream and the
        next stream uses a fresh connection id. The room a connection was connected to
        is server state, so it is forgotten whenever a stream opens or closes.
        """
        self._forget_room()
        url = (
            f"{self.base_url}/agents/{self.agent_id}/events?connection_id={self.connection_id}"
            "&scope=all&filter=all&start_from=head&client=ownership-gate"
        )
        headers = {**self._auth(), "Accept": "text/event-stream"}
        if self.last_event_id:
            headers["Last-Event-ID"] = self.last_event_id
        gone = threading.Event()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=headers), timeout=STREAM_TIMEOUT_SECONDS
            ) as stream:
                threading.Thread(target=self._beat, args=(gone,), daemon=True).start()
                for frame in parse_frames(_lines_until(stream, gone)):
                    if frame.event == "evicted":
                        self.connection_id = str(uuid.uuid4())
                        raise SwitchError(f"evicted: {frame.data}")
                    if frame.id:
                        self.last_event_id = frame.id
                    message = to_message(frame.data) if isinstance(frame.data, dict) else None
                    if message is not None:
                        yield message
        finally:
            gone.set()
            self._forget_room()

    def _forget_room(self) -> None:
        with self._post_lock:
            self._room = None

    def _beat(self, gone: threading.Event) -> None:
        """Beat until the stream ends. Marks the connection gone when the server forgot
        it or several beats in a row failed; the reader stops at its next line, which
        the server's 15 s keepalive guarantees."""
        url = f"{self.base_url}/agents/{self.agent_id}/connection/beat"
        misses = 0
        while not gone.wait(BEAT_SECONDS):
            try:
                _post(url, self.api_key, {"connection_id": self.connection_id})
                misses = 0
            except SwitchError as err:
                misses += 1
                if err.status in CONNECTION_GONE or misses >= BEAT_MISSES_ALLOWED:
                    gone.set()

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}


def _lines_until(stream: Iterable[bytes], gone: threading.Event) -> Iterator[str]:
    """Decoded lines of `stream`; raises once `gone` is set, checked at every line."""
    for raw in stream:
        if gone.is_set():
            raise SwitchError("connection lost: heartbeat failed")
        yield raw.decode("utf-8")


def _post(url: str, token: str, body: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        raise SwitchError(
            f"{url} returned {err.code}: {err.read().decode('utf-8', 'replace')}", err.code
        ) from err
    except urllib.error.URLError as err:
        raise SwitchError(f"{url} unreachable: {err.reason}") from err
    return json.loads(text) if text else {}
