"""People in Mattermost: the two humans of a live run, acting in Mattermost itself.

Each person posts in the Mattermost channel Switch bridged to the room, as their own
Mattermost account, and the author presses Approve or Decline on the card Switch renders
there. Switch sees bridged humans with no Switch user id; who they are is Switch's decision,
from the account each person claimed (``flip demo``) and each agent's addressing policy.

Reading cards and the reviewer's attempt to answer the author's card go through the
gateway, so that Switch's own 403 stays the refusal under test.
"""

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from flipside.room.run import Card, Log
from flipside.room.switch_client import Http

ACTION_NAMES = {"approve": "Approve", "decline": "Decline"}


class MattermostError(RuntimeError):
    """A Mattermost API call failed."""


@dataclass
class MM:
    """A minimal Mattermost REST v4 client for one signed-in account."""

    base: str
    token: str = ""

    def call(self, method: str, path: str, body: Any = None) -> Any:
        req = urllib.request.Request(
            f"{self.base}/api/v4{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if path == "/users/login":
                    self.token = r.headers["Token"]
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise MattermostError(f"{method} {path}: HTTP {e.code}: {detail}") from e

    def login(self, user: str, password: str) -> "MM":
        self.call("POST", "/users/login", {"login_id": user, "password": password})
        return self


_NUMBERED = re.compile(r"^\d+\.\s+")


def card_actions(post: dict[str, Any]) -> dict[str, str]:
    """The buttons on a Switch card post: label -> action id. Switch numbers its buttons
    ("1. Approve") so people can also type the number; the label is matched without it."""
    out: dict[str, str] = {}
    for att in (post.get("props") or {}).get("attachments") or []:
        for act in att.get("actions") or []:
            if act.get("id") and act.get("name"):
                out[_NUMBERED.sub("", str(act["name"]))] = str(act["id"])
    return out


def post_text(post: dict[str, Any]) -> str:
    """Everything a person reads on a post: its message and its attachments' text."""
    parts = [str(post.get("message") or "")]
    for att in (post.get("props") or {}).get("attachments") or []:
        for k in ("pretext", "title", "text", "fallback"):
            parts.append(str(att.get(k) or ""))
        for f in att.get("fields") or []:
            parts.append(f"{f.get('title') or ''} {f.get('value') or ''}")
    return "\n".join(parts)


@dataclass
class MattermostHumans:
    """``Humans`` for a run whose rooms are Mattermost channels."""

    people: dict[str, MM]
    channels: dict[str, str]
    gateway: dict[str, Http]
    agents: dict[str, str]
    private: str
    log: Log
    seen: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    press_wait: float = 20.0

    def say(self, who: str, room: str, body: str, mention_agent: str | None = None) -> str:
        """Post as ``who`` in Mattermost. A mention is plain ``@<agent name>`` text, as a
        person types it; Switch decides whether it addresses the agent."""
        post = self.people[who].call(
            "POST", "/posts", {"channel_id": self.channels[room], "message": body}
        )
        self.log(f"{who} posted in Mattermost {post['id']}: {body.splitlines()[0][:80]}")
        return str(post["id"])

    def pending_cards(self, who: str) -> list[Card]:
        out = []
        for row in self.gateway[who].get("/gateway/agent-sessions/approvals") or []:
            if row.get("roomId") != self.private or row.get("state") != "open":
                continue
            rid = str(row["requestId"])
            self.seen[rid] = (str(row["agentId"]), str(row["sessionId"]), str(row["title"]))
            out.append(Card(rid, str(row["title"])))
        return out

    def answer_card(self, who: str, card: str, answer: str) -> None:
        agent, session, title = self.seen[card]
        if who != "author":
            path = f"/gateway/agent-sessions/{agent}/{session}/approvals/{card}/answer"
            self.gateway[who].post(path, {"answer": answer})
            self.log(f"{who} answered card {card[:8]} through the gateway: {answer}")
            return
        post, action = self.find_button(title, ACTION_NAMES[answer])
        self.people[who].call("POST", f"/posts/{post}/actions/{action}", {})
        self.log(f"author pressed {ACTION_NAMES[answer]} on card {card[:8]} in Mattermost")

    def find_button(self, title: str, name: str) -> tuple[str, str]:
        """The newest card post in the author's private channel that shows ``title`` and
        still has the ``name`` button. Switch renders the card shortly after it opens."""
        mm = self.people["author"]
        deadline = time.monotonic() + self.press_wait
        while True:
            page = mm.call("GET", f"/channels/{self.channels[self.private]}/posts?per_page=60")
            for pid in page.get("order", []):
                p = page["posts"][pid]
                acts = card_actions(p)
                if name in acts and title in post_text(p):
                    return str(pid), acts[name]
            if time.monotonic() > deadline:
                shown = [
                    json.dumps((p.get("props") or {}).get("attachments"))[:600]
                    for p in page["posts"].values()
                    if title in post_text(p)
                ]
                raise MattermostError(
                    f"no card post with {name!r} for {title!r} in Mattermost; "
                    f"card attachments seen: {shown}"
                )
            time.sleep(1.5)
