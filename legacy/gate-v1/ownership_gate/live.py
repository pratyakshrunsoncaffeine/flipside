"""The author's gate agent, live in Switch.

Runs on the author's machine, because their Entire sessions never leave it. It polls
GitHub for the author's open PRs (Switch has no webhook intake), opens one room per PR
from `templates/pr-room.yaml`, posts the gaps, and checks the author's answers.
Only messages whose sender is the author's chat account are treated as answers; the
agent's `owner` addressing policy also stops anyone else from driving it.

State in `state_dir` survives a restart: `rooms.json` (PR to room), `gates.json` (PR to
the head commit whose opening was posted), `events.jsonl` (every message posted or
read) and `cursor.txt` (the last event-stream id). On restart a gate is rebuilt by
replaying the author's logged answers, so nobody is asked twice.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ownership_gate import github, render
from ownership_gate.controller import GateController
from ownership_gate.entire import load_session
from ownership_gate.events import AGENT, HUMAN, EventLog, RoomEvent, read_events
from ownership_gate.model import PullRequest
from ownership_gate.switch_client import ChatMessage, SwitchAgent, SwitchError

log = logging.getLogger("ownership_gate")
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "pr-room.yaml"
ROOM_ID_KEYS = ("room_id", "id")
MIN_RECONNECT_SECONDS = 2.0
MAX_RECONNECT_SECONDS = 60.0


@dataclass
class LiveConfig:
    repo: str
    author: str
    chat_user: str
    repo_dir: Path
    agent_name: str
    reviewer_chat: str = ""
    reviewer_agent: str = ""
    poll_seconds: float = 30.0
    ci_grace_seconds: float = 600.0
    state_dir: Path = Path(".ogate")


@dataclass(frozen=True)
class Outgoing:
    pr_key: str
    room: str
    text: str
    thread_id: str | None = None


@dataclass
class LiveGate:
    config: LiveConfig
    agent: SwitchAgent
    controller: GateController = field(init=False)
    rooms: dict[str, str] = field(default_factory=dict)
    opened: dict[str, str] = field(default_factory=dict)
    outbox: list[Outgoing] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    clock: Callable[[], float] = time.monotonic
    first_seen: dict[tuple[str, str], float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.controller = GateController(
            reviewer=self.config.reviewer_chat,
            handles={self.config.author.casefold(): self.config.chat_user},
        )
        self.events = EventLog(self.config.state_dir / "events.jsonl")
        self.rooms = _load_json(self.config.state_dir / "rooms.json")
        self.opened = _load_json(self.config.state_dir / "gates.json")
        cursor = self.config.state_dir / "cursor.txt"
        if cursor.exists():
            self.agent.last_event_id = cursor.read_text(encoding="utf-8").strip() or None

    def run(self) -> None:
        threading.Thread(target=self._listen_forever, daemon=True).start()
        while True:
            try:
                self.poll_once()
            except Exception:
                log.exception("polling %s failed; retrying next round", self.config.repo)
            time.sleep(self.config.poll_seconds)

    def poll_once(self) -> None:
        self.flush_outbox()
        pulls = github.open_pulls(self.config.repo, self.config.author)
        self._prune_first_seen({f"{self.config.repo}#{n}" for n, _ in pulls})
        for number, head_sha in pulls:
            key = f"{self.config.repo}#{number}"
            with self.lock:
                if self.controller.head_sha(key) == head_sha:
                    continue
            try:
                self.open_gate(github.fetch_pull_request(self.config.repo, number))
            except Exception:
                log.exception("could not open the gate for %s", key)

    def open_gate(self, pr: PullRequest) -> None:
        """Open the gate for a new head commit, or rebuild it after a restart.

        The room comes first, so a failure leaves no gate behind. A failed opening post
        forgets the gate so the next poll retries; later messages wait in the outbox.
        """
        with self.lock:
            if self.controller.is_current(pr):
                return
            if self.opened.get(pr.key) == pr.head_sha and pr.key in self.rooms:
                self._restore(pr)
                return
            if not self._ci_settled(pr):
                return
            room = self._room_for(pr)
            session = load_session(self.config.repo_dir, pr.checkpoint_ids)
            opening, *rest = self.controller.open(pr, session)
        if not self._send(Outgoing(pr.key, room, opening)):
            with self.lock:
                self.controller.forget(pr.key)
            return
        with self.lock:
            self.opened[pr.key] = pr.head_sha
            _save_json(self.config.state_dir / "gates.json", self.opened)
        self._post([Outgoing(pr.key, room, text) for text in rest])

    def handle(self, message: ChatMessage) -> None:
        with self.lock:
            pr_key = next((k for k, r in self.rooms.items() if r == message.room_id), None)
        if pr_key is None or message.sender_name.casefold() != self.config.chat_user.casefold():
            return
        self.events.add(message.room_id, message.sender_name, HUMAN, message.body)
        with self.lock:
            replies = self.controller.on_message(pr_key, self.config.author, message.body)
        self._post([Outgoing(pr_key, message.room_id, r, message.thread_id) for r in replies])

    def flush_outbox(self) -> None:
        with self.lock:
            pending, self.outbox = self.outbox, []
        self._post(pending)

    def _restore(self, pr: PullRequest) -> None:
        """Rebuild a gate whose opening was posted before a restart, without posting.
        The author's answers since that opening are replayed in order."""
        room = self.rooms[pr.key]
        session = load_session(self.config.repo_dir, pr.checkpoint_ids)
        self.controller.open(pr, session)
        for event in _answers_since_opening(self._room_events(room)):
            self.controller.on_message(pr.key, self.config.author, event.text)
        log.info("restored the gate for %s from the room log", pr.key)

    def _room_events(self, room: str) -> list[RoomEvent]:
        path = self.config.state_dir / "events.jsonl"
        return [e for e in read_events(path) if e.room == room] if path.exists() else []

    def _listen_forever(self) -> None:
        delay = MIN_RECONNECT_SECONDS
        cursor = self.config.state_dir / "cursor.txt"
        while True:
            started = self.clock()
            try:
                for message in self.agent.messages():
                    try:
                        self.handle(message)
                    except Exception:
                        log.exception("could not handle message %s", message.message_id)
                    if self.agent.last_event_id:
                        _write_atomic(cursor, self.agent.last_event_id)
            except (SwitchError, OSError, ValueError) as err:
                log.warning("event stream dropped (%s); reconnecting in %ss", err, delay)
            except Exception:
                log.exception("event stream failed; reconnecting in %ss", delay)
            if self.clock() - started >= MAX_RECONNECT_SECONDS:
                delay = MIN_RECONNECT_SECONDS
            time.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_SECONDS)

    def _ci_settled(self, pr: PullRequest) -> bool:
        """True once every check run has finished, or the grace period since this head
        was first seen has passed. A gate opened seconds after a push would see no CI
        yet and ask an honest author why CI never reported."""
        if pr.checks and all(c.conclusion is not None for c in pr.checks):
            return True
        first_seen = self.first_seen.setdefault((pr.key, pr.head_sha), self.clock())
        return self.clock() - first_seen >= self.config.ci_grace_seconds

    def _prune_first_seen(self, open_keys: set[str]) -> None:
        with self.lock:
            self.first_seen = {k: t for k, t in self.first_seen.items() if k[0] in open_keys}

    def _room_for(self, pr: PullRequest) -> str:
        if pr.key in self.rooms:
            return self.rooms[pr.key]
        result = self.agent.create_room(TEMPLATE.read_text(encoding="utf-8"), self._inputs(pr))
        room_id = _room_id(result)
        if not room_id:
            raise SwitchError(f"create_room_from_yaml returned no room id: {result!r}")
        self.rooms[pr.key] = room_id
        _save_json(self.config.state_dir / "rooms.json", self.rooms)
        if self.config.reviewer_agent:
            try:
                self.agent.op(
                    "invite_agent_to_room",
                    {"room_id": room_id, "agent_name": self.config.reviewer_agent},
                )
            except SwitchError as err:
                log.error("could not invite %s to %s: %s", self.config.reviewer_agent, room_id, err)
        return room_id

    def _inputs(self, pr: PullRequest) -> dict[str, Any]:
        return {
            "slug": f"pr-{pr.repo.replace('/', '-')}-{pr.number}".lower(),
            "title": f"{pr.key}: {pr.title}",
            "gate_agent": self.config.agent_name,
        }

    def _post(self, messages: list[Outgoing]) -> None:
        """Post in order. On the first failure, the rest wait in the outbox for the next
        poll, so a reviewer brief never arrives before the reply it follows."""
        for i, out in enumerate(messages):
            if not self._send(out):
                with self.lock:
                    self.outbox = [*messages[i:], *self.outbox]
                return

    def _send(self, out: Outgoing) -> bool:
        try:
            self.agent.post(out.room, out.text, out.thread_id)
        except (SwitchError, OSError) as err:
            log.error("could not post to %s for %s: %s", out.room, out.pr_key, err)
            return False
        self.events.add(out.room, self.config.agent_name, AGENT, out.text)
        return True


def _answers_since_opening(events: list[RoomEvent]) -> list[RoomEvent]:
    """The author's messages after the latest opening post in a room's log."""
    openings = [i for i, e in enumerate(events) if e.kind == AGENT and render.is_opening(e.text)]
    start = openings[-1] + 1 if openings else len(events)
    return [e for e in events[start:] if e.kind == HUMAN]


def _room_id(result: Any) -> str:
    """Find the room id in a `create_room_from_yaml` result, whose exact shape varies."""
    if isinstance(result, dict):
        for key in ROOM_ID_KEYS:
            if isinstance(result.get(key), str):
                return result[key]
        for value in result.values():
            if isinstance(value, dict | list):
                found = _room_id(value)
                if found:
                    return found
    if isinstance(result, list):
        for item in result:
            found = _room_id(item)
            if found:
                return found
    return ""


def _load_json(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save_json(path: Path, data: dict[str, str]) -> None:
    _write_atomic(path, json.dumps(data, indent=2))


def _write_atomic(path: Path, text: str) -> None:
    """Write via a temporary file, so a crash mid-write never leaves a broken file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
