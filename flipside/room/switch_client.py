"""SwitchTransport: one agent's view of a real Switch server (switch-core 0.31.0).

Facts this relies on were proven in kill tests K1, K2 and K4 (docs/BUILD.md section 9):

- An agent posts with its API key (``POST /agents/{id}/message``) and attaches files with
  ``POST /agents/{id}/rooms/{room}/media``. Both return the Switch message id.
- An agent key cannot read the gateway transcript, so the agent reads the room through its
  owner's gateway session (``GET /gateway/chats/{room}/messages``), which carries the
  message id, ``seq`` and the sender's ``agentId`` or ``userId``.
- Whether a message addressed this agent is Switch's decision, delivered on the agent's
  event stream as ``payload.addressed`` with the same message id. ``EventTap`` keeps that
  map and its stream cursor in a file, so a restarted agent resumes where it stopped.
- Approval cards are opened in an agent session; outcomes stay listed until acknowledged,
  so a restarted agent sees them again and rebuilds its state from the transcript.
"""

import contextlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any

from flipside.room.agents import write_atomic
from flipside.room.protocol import Msg
from flipside.room.transport import Forbidden, Outcome

DEFAULT_BASE = "http://127.0.0.1:52370"
PAGE = 200
ADDRESSED_WAIT = 8.0


class SwitchError(RuntimeError):
    """Switch answered with an HTTP error other than 403."""

    def __init__(self, status: int, method: str, path: str, body: str) -> None:
        super().__init__(f"{method} {path}: HTTP {status}: {body[:300]}")
        self.status = status


class Http:
    """A small JSON client: cookie session for people, bearer token for agents."""

    def __init__(self, base: str = DEFAULT_BASE, bearer: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.bearer = bearer
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        raw: bytes | None = None,
        content_type: str = "application/json",
    ) -> Any:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", content_type)
        if self.bearer:
            req.add_header("Authorization", f"Bearer {self.bearer}")
        try:
            with self._opener.open(req, timeout=30) as r:
                payload = r.read()
                if r.headers.get_content_type() == "application/json":
                    return json.loads(payload) if payload else None
                return payload
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            if e.code == 403:
                raise Forbidden(_detail(text)) from None
            raise SwitchError(e.code, method, path, text) from None

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, body if body is not None else {})

    def put(self, path: str, body: dict[str, Any]) -> Any:
        return self.request("PUT", path, body)

    def login(self, email: str, password: str) -> None:
        res = self.post("/gateway/auth/login", {"email": email, "password": password}) or {}
        token = res.get("access_token") or res.get("token")
        if token:
            self.bearer = token


def _detail(text: str) -> str:
    """The human message inside a Switch error body."""
    try:
        obj = json.loads(text)
    except ValueError:
        return text
    if isinstance(obj, dict):
        d = obj.get("detail", obj)
        if isinstance(d, dict):
            return str(d.get("message") or d)
        return str(obj.get("message") or d)
    return text


def multipart(field_name: str, filename: str, data: bytes, mimetype: str) -> tuple[bytes, str]:
    """One-file multipart/form-data body and its content type."""
    boundary = uuid.uuid4().hex
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="{field_name}"; '
        f'filename="{filename}"\r\nContent-Type: {mimetype}\r\n\r\n'
    ).encode()
    return head + data + f"\r\n--{boundary}--\r\n".encode(), (
        f"multipart/form-data; boundary={boundary}"
    )


@dataclass
class EventTap:
    """The agent's live connection: an event stream plus the 2-second heartbeat.

    Records ``addressed`` per message id and the last stream event id. Both persist in
    ``cursor_path``; a new tap on the same file sends that id as ``Last-Event-ID``.
    """

    base: str
    agent_id: str
    api_key: str
    rooms: tuple[str, ...]
    cursor_path: Path
    addressed: dict[str, bool] = field(default_factory=dict)
    last_event_id: str | None = None
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    opened: threading.Event = field(default_factory=threading.Event)
    notes: list[str] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.cursor_path.exists():
            raw = json.loads(self.cursor_path.read_text(encoding="utf-8"))
            self.addressed = {str(k): bool(v) for k, v in raw.get("addressed", {}).items()}
            self.last_event_id = raw.get("last_event_id")

    def start(self) -> "EventTap":
        threading.Thread(target=self._stream, daemon=True).start()
        threading.Thread(target=self._beat, daemon=True).start()
        self.opened.wait(10)
        return self

    def stop(self) -> None:
        self._stop.set()
        self._save()

    def _save(self) -> None:
        with self._lock:
            state = {"addressed": self.addressed, "last_event_id": self.last_event_id}
        write_atomic(self.cursor_path, json.dumps(state, sort_keys=True))

    def _stream(self) -> None:
        """Hold the event stream open, reconnecting with ``Last-Event-ID`` after a drop.

        A restarted agent may find its rooms still claimed by the dead process's stream
        until that stream's heartbeat expires (6 seconds), so opening is retried."""
        while not self._stop.is_set():
            url = (
                f"{self.base}/agents/{self.agent_id}/events?connection_id={self.connection_id}"
                f"&scope=all&filter=all&start_from=head&rooms={','.join(self.rooms)}"
            )
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {self.api_key}")
            req.add_header("Accept", "text/event-stream")
            with self._lock:
                last = self.last_event_id
            if last:
                req.add_header("Last-Event-ID", last)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self.opened.set()
                    for line in r:
                        if self._stop.is_set():
                            return
                        self._line(line.decode(errors="replace").rstrip("\r\n"))
            except Exception as e:  # recorded; the agent keeps working from the transcript
                note = f"event stream: {type(e).__name__} {getattr(e, 'code', '')}".strip()
                if not self.notes or self.notes[-1] != note:
                    self.notes.append(note)
            self._stop.wait(1.0)

    def _line(self, s: str) -> None:
        if s.startswith("id:"):
            with self._lock:
                self.last_event_id = s[3:].strip()
        elif s.startswith("data:"):
            try:
                ev = json.loads(s[5:].strip())
            except ValueError:
                return
            if not isinstance(ev, dict):
                return
            if ev.get("type") == "gap":
                self.notes.append(f"event stream gap: {json.dumps(ev)[:160]}")
            p = ev.get("payload") or {}
            if ev.get("type") == "message" and p.get("message_id"):
                with self._lock:
                    self.addressed[str(p["message_id"])] = bool(p.get("addressed"))
                self._save()

    def _beat(self) -> None:
        http = Http(self.base, bearer=self.api_key)
        while not self._stop.is_set():
            with contextlib.suppress(Forbidden, SwitchError, OSError):
                http.post(
                    f"/agents/{self.agent_id}/connection/beat",
                    {"connection_id": self.connection_id},
                )
            self._stop.wait(2)

    def get(self, message_id: str) -> bool | None:
        with self._lock:
            return self.addressed.get(message_id)


def sender_of(m: dict[str, Any]) -> str:
    s = m.get("sender") or {}
    if s.get("agentId"):
        return f"agent:{s['agentId']}"
    if s.get("userId"):
        return f"user:{s['userId']}"
    return f"{s.get('kind') or 'system'}:{s.get('clientId') or ''}"


class SwitchTransport:
    """``Transport`` for one agent on a real Switch server."""

    def __init__(
        self,
        *,
        base: str,
        agent_id: str,
        api_key: str,
        name: str,
        owner: Http,
        rooms: tuple[str, ...],
        session_id: str,
        cursor_path: Path,
        listen: bool = True,
    ) -> None:
        """``listen=False`` opens no event stream: the transport can post and read, but
        reads carry no addressing decision. Use it for a second handle on an agent whose
        process already holds the stream (Switch allows one stream per agent)."""
        self.base = base
        self.agent_id = agent_id
        self.name = name
        self.agent = Http(base, bearer=api_key)
        self.owner = owner
        self.session_id = session_id
        self.listen = listen
        self.tap = EventTap(base, agent_id, api_key, rooms, cursor_path)
        if listen:
            self.tap.start()
        self._cache: dict[str, dict[int, dict[str, Any]]] = {}
        self._started = False

    @property
    def me(self) -> str:
        return f"agent:{self.agent_id}"

    def close(self) -> None:
        if self.listen:
            self.tap.stop()

    def _fetch(self, room: str) -> list[dict[str, Any]]:
        """Every message in the room, oldest first, paging back only past what is cached."""
        cache = self._cache.setdefault(room, {})
        known = max(cache) if cache else 0
        before: int | None = None
        while True:
            q = f"?limit={PAGE}" + (f"&beforeSeq={before}" if before else "")
            page = self.owner.get(f"/gateway/chats/{room}/messages{q}")
            rows = page.get("messages", []) if isinstance(page, dict) else page
            for m in rows:
                cache[int(m["seq"])] = m
            seqs = [int(m["seq"]) for m in rows]
            if not rows or not page.get("hasMore") or min(seqs) <= known:
                break
            before = min(seqs)
        return [cache[s] for s in sorted(cache)]

    def _msgs(self, room: str) -> list[Msg]:
        return [
            Msg(
                str(m["messageId"]),
                int(m["seq"]),
                room,
                sender_of(m),
                str((m.get("sender") or {}).get("name") or ""),
                str(m.get("body") or ""),
                self.tap.get(str(m["messageId"])),
            )
            for m in self._fetch(room)
        ]

    def read(self, room: str) -> list[Msg]:
        """The room transcript. Waits briefly for Switch's addressing decision on any message
        that tags this agent, so a request is never judged before Switch has judged it."""
        deadline = time.monotonic() + ADDRESSED_WAIT
        while True:
            msgs = self._msgs(room)
            pending = [
                m
                for m in msgs
                if m.sender != self.me
                and m.addressed is None
                and m.body.startswith(f"@{self.name}")
            ]
            if not self.listen or not pending or time.monotonic() > deadline:
                return msgs
            time.sleep(0.25)

    def post(self, room: str, body: str) -> str:
        res = self.agent.post(
            f"/agents/{self.agent_id}/message", {"room_id": room, "content": body}
        )
        return str(res["event_id"])

    def upload(self, room: str, name: str, data: bytes) -> str:
        body, ctype = multipart("file", name, data, "application/json")
        res = self.agent.request(
            "POST", f"/agents/{self.agent_id}/rooms/{room}/media", raw=body, content_type=ctype
        )
        return str(res["mxc"])

    def download(self, room: str, uri: str) -> bytes:
        q = urllib.parse.quote(uri, safe="")
        data = self.agent.get(f"/agents/{self.agent_id}/rooms/{room}/media?mxc={q}")
        if isinstance(data, bytes):
            return data
        return json.dumps(data, separators=(",", ":")).encode()

    def open_card(self, room: str, card: str, title: str, detail: str) -> None:
        if not self._started:
            with contextlib.suppress(SwitchError):
                self.agent.post(
                    f"/agent-sessions/{self.session_id}/started", {"start_source": "room"}
                )
            self._started = True
        self.agent.post(
            f"/agent-sessions/{self.session_id}/approvals",
            {
                "request_id": card,
                "turn_id": card,
                "kind": "approval",
                "title": title,
                "detail": detail,
                "options": [
                    {"id": "approve", "label": "Approve", "decision": "accept"},
                    {"id": "decline", "label": "Decline", "decision": "decline"},
                ],
                "questions": [],
                "room_id": room,
                "thread_id": None,
                "expires_at": None,
            },
        )

    def outcomes(self) -> list[Outcome]:
        """Answered cards of this agent session. Never acknowledged, so a restart sees them."""
        rows = self.agent.get("/agent-sessions/approvals/outcomes") or []
        return [
            Outcome(str(o["requestId"]), str(o["answer"]), str(o.get("answeredBy") or ""))
            for o in rows
            if o.get("sessionId") == self.session_id and o.get("answer") is not None
        ]


@contextlib.contextmanager
def transports(*ts: SwitchTransport) -> Iterator[tuple[SwitchTransport, ...]]:
    """Close every transport's event stream on exit."""
    try:
        yield ts
    finally:
        for t in ts:
            t.close()
