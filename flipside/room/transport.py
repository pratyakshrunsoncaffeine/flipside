"""Transport between agents and Switch.

``Transport`` is what an agent uses: read a room, post, attach a file, open an
approval card, read card outcomes. ``SwitchTransport`` (switch_client.py) talks to
a real Switch server; ``FakeTransport`` talks to ``FakeSwitch``, an in-process hub
that applies the rules Switch was shown to apply in kill tests K1, K2 and K4:
scoped addressing with Switch's own refusal, and cards only the addresser can answer.
"""

import hashlib
import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from flipside.room.protocol import Msg

REFUSAL = (
    "You're not permitted to direct messages to me in this room - my operator has "
    "restricted who can address me here."
)
FORBIDDEN_ANSWER = "You may not address this agent, so you may not answer it."


class Forbidden(PermissionError):
    """Switch refused the call (HTTP 403)."""


@dataclass(frozen=True)
class Outcome:
    card: str
    answer: str
    answered_by: str


class Transport(Protocol):
    """One agent's view of Switch."""

    @property
    def me(self) -> str: ...

    def read(self, room: str) -> list[Msg]: ...

    def post(self, room: str, body: str) -> str: ...

    def upload(self, room: str, name: str, data: bytes) -> str: ...

    def download(self, room: str, uri: str) -> bytes: ...

    def open_card(self, room: str, card: str, title: str, detail: str) -> None: ...

    def outcomes(self) -> list[Outcome]: ...


@dataclass
class Rule:
    """One addressing rule: owner, owner's agents, or listed senders, optionally per room."""

    owner: bool = False
    owner_agents: bool = False
    agents: tuple[str, ...] = ()
    users: tuple[str, ...] = ()
    rooms: tuple[str, ...] = ()


@dataclass
class _Agent:
    id: str
    name: str
    owner: str
    policy: list[Rule] = field(default_factory=lambda: [Rule(owner=True)])


@dataclass
class _Card:
    agent: str
    room: str
    title: str
    detail: str
    answer: str | None = None
    answered_by: str | None = None


class FakeSwitch:
    """In-process Switch: rooms, members, agents, addressing, refusals, media, cards."""

    def __init__(self) -> None:
        self.names: dict[str, str] = {}
        self.agents: dict[str, _Agent] = {}
        self.rooms: dict[str, set[str]] = {}
        self.messages: list[Msg] = []
        self.media: dict[str, bytes] = {}
        self.cards: dict[str, _Card] = {}
        self._seq = itertools.count(1)
        self._system: set[str] = set()
        self.log: list[str] = []

    def user(self, uid: str, name: str) -> str:
        sid = f"user:{uid}"
        self.names[sid] = name
        return sid

    def agent(self, aid: str, name: str, owner: str) -> str:
        sid = f"agent:{aid}"
        self.names[sid] = name
        self.agents[sid] = _Agent(sid, name, owner)
        return sid

    def room(self, rid: str, members: Sequence[str]) -> str:
        self.rooms[rid] = set(members)
        return rid

    def set_policy(self, agent: str, rules: list[Rule], by: str) -> None:
        if self.agents[agent].owner != by:
            raise Forbidden("only the owner sets an agent's addressing policy")
        self.agents[agent].policy = rules

    def may_address(self, sender: str, agent: str, room: str) -> bool:
        a = self.agents[agent]
        for r in a.policy:
            if r.rooms and room not in r.rooms:
                continue
            if r.owner and sender == a.owner:
                return True
            if r.owner_agents and sender in self.agents and self.agents[sender].owner == a.owner:
                return True
            if sender in r.agents or sender in r.users:
                return True
        return False

    def _mentions(self, body: str, room: str) -> list[str]:
        return [
            a
            for a in self.rooms[room]
            if a in self.agents and body.startswith(f"@{self.agents[a].name}")
        ]

    def post(self, sender: str, room: str, body: str, system: bool = False) -> str:
        """Post a message. Switch's own refusals are ``system`` posts: they are not
        checked for mentions, so a refusal never triggers another refusal."""
        if sender not in self.rooms.get(room, set()):
            raise Forbidden(f"{self.names.get(sender, sender)} is not in room {room}")
        seq = next(self._seq)
        mid = f"m{seq}"
        self.messages.append(Msg(mid, seq, room, sender, self.names[sender], body))
        if system:
            self._system.add(mid)
            return mid
        for agent in self._mentions(body, room):
            if agent != sender and not self.may_address(sender, agent, room):
                self.post(agent, room, f"@{self.names[sender]} {REFUSAL}", system=True)
        return mid

    def read(self, reader: str, room: str) -> list[Msg]:
        if reader not in self.rooms.get(room, set()):
            raise Forbidden(f"{reader} is not in room {room}")
        out = []
        for m in self.messages:
            if m.room != room:
                continue
            addressed = None
            if reader in self.agents:
                addressed = (
                    m.id not in self._system
                    and reader in self._mentions(m.body, room)
                    and self.may_address(m.sender, reader, room)
                )
            out.append(Msg(m.id, m.seq, m.room, m.sender, m.sender_name, m.body, addressed))
        return out

    def upload(self, sender: str, room: str, data: bytes) -> str:
        if sender not in self.rooms.get(room, set()):
            raise Forbidden("not in room")
        uri = f"mxc://fake/{hashlib.sha256(data).hexdigest()[:24]}"
        self.media[uri] = data
        return uri

    def download(self, reader: str, room: str, uri: str) -> bytes:
        if reader not in self.rooms.get(room, set()):
            raise Forbidden("not in room")
        return self.media[uri]

    def open_card(self, agent: str, room: str, card: str, title: str, detail: str) -> None:
        if card not in self.cards:
            self.cards[card] = _Card(agent, room, title, detail)

    def answer(self, user: str, card: str, answer: str) -> None:
        """A human answers a card. Only someone who may address the agent may answer."""
        c = self.cards[card]
        if user not in self.rooms[c.room] or not self.may_address(user, c.agent, c.room):
            raise Forbidden(FORBIDDEN_ANSWER)
        if c.answer is None:
            c.answer, c.answered_by = answer, user

    def outcomes(self, agent: str) -> list[Outcome]:
        return [
            Outcome(k, c.answer, c.answered_by or "")
            for k, c in self.cards.items()
            if c.agent == agent and c.answer is not None
        ]


class FakeTransport:
    """An agent's Transport onto a FakeSwitch."""

    def __init__(self, hub: FakeSwitch, agent: str) -> None:
        self.hub = hub
        self._me = agent

    @property
    def me(self) -> str:
        return self._me

    def read(self, room: str) -> list[Msg]:
        return self.hub.read(self._me, room)

    def post(self, room: str, body: str) -> str:
        return self.hub.post(self._me, room, body)

    def upload(self, room: str, name: str, data: bytes) -> str:
        return self.hub.upload(self._me, room, data)

    def download(self, room: str, uri: str) -> bytes:
        return self.hub.download(self._me, room, uri)

    def open_card(self, room: str, card: str, title: str, detail: str) -> None:
        self.hub.open_card(self._me, room, card, title, detail)

    def outcomes(self) -> list[Outcome]:
        return self.hub.outcomes(self._me)
