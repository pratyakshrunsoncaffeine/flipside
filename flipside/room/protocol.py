"""Room protocol (docs/BUILD.md section 6).

Every machine message is one human-readable line, then one fenced JSON block.
Parsers read only the JSON block, and accept a message only from the sender the
table names, checked by Switch sender id, never by message text.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

TYPES = ("seal", "questions", "request", "disclosure", "withheld", "verdict", "brief")
AUTHOR_AGENT, REVIEWER_AGENT = "author_agent", "reviewer_agent"
SENDER = {
    "seal": AUTHOR_AGENT,
    "questions": REVIEWER_AGENT,
    "request": REVIEWER_AGENT,
    "disclosure": AUTHOR_AGENT,
    "withheld": AUTHOR_AGENT,
    "verdict": REVIEWER_AGENT,
    "brief": REVIEWER_AGENT,
}
MAX_LEAVES = 8
WITHHELD_REASONS = ("author", "secret_scan", "session_changed")
_BLOCK = re.compile(r"```json\n(.*?)\n```", re.S)
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_ANSWER = re.compile(r"^\s*Q(\d+):\s*(.*)\Z", re.S)


@dataclass(frozen=True)
class Msg:
    """One room message as an agent sees it.

    ``sender`` is a stable Switch identity: ``agent:<agent id>`` or ``user:<user id>``.
    ``addressed`` is Switch's own decision for the reading agent (None when unknown).
    """

    id: str
    seq: int
    room: str
    sender: str
    sender_name: str
    body: str
    addressed: bool | None = None


def encode(line: str, obj: dict[str, Any]) -> str:
    """One human line, then one fenced JSON block."""
    if "\n" in line:
        raise ValueError("the human line must be a single line")
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{line}\n```json\n{payload}\n```"


def decode(body: str) -> dict[str, Any] | None:
    """The JSON object of a machine message, or None when there is not exactly one block,
    it is not an object, or its type or version is unknown."""
    blocks = _BLOCK.findall(body)
    if len(blocks) != 1:
        return None
    try:
        obj = json.loads(blocks[0])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or obj.get("t") not in TYPES or obj.get("v") != 1:
        return None
    if isinstance(obj.get("v"), bool):
        return None
    return obj


def accept(msg: Msg, roles: dict[str, str]) -> dict[str, Any] | None:
    """Decode ``msg`` and keep it only when its sender holds the role the type requires.

    ``roles`` maps AUTHOR_AGENT and REVIEWER_AGENT to Switch sender ids.
    """
    obj = decode(msg.body)
    if obj is None:
        return None
    return obj if roles.get(SENDER[obj["t"]]) == msg.sender else None


def _int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


@dataclass(frozen=True)
class Request:
    """A validated ``request``: the only reviewer input that reaches the author's side."""

    commit: str
    q: int
    leaves: tuple[int, ...]


def parse_request(obj: dict[str, Any], n: int) -> Request | None:
    """Fixed schema: exactly t, v, commit (40 hex), q (int >= 1), leaves (1 to 8 distinct
    ints below n). Anything else, including any free text, is dropped."""
    if sorted(obj) != ["commit", "leaves", "q", "t", "v"] or obj["t"] != "request":
        return None
    commit, q, leaves = obj["commit"], obj["q"], obj["leaves"]
    if not isinstance(commit, str) or not _HEX40.match(commit) or not _int(q) or q < 1:
        return None
    if not isinstance(leaves, list) or not 1 <= len(leaves) <= MAX_LEAVES:
        return None
    if not all(_int(i) and 0 <= i < n for i in leaves) or len(set(leaves)) != len(leaves):
        return None
    return Request(commit, q, tuple(leaves))


def parse_answer(body: str) -> tuple[int, str] | None:
    """A human answer: free text starting ``Q<k>:``; no JSON."""
    m = _ANSWER.match(body)
    if m is None or "```json" in body:
        return None
    return int(m.group(1)), m.group(2).strip()
