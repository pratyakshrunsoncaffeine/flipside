"""``flip chat``: what a person does in the PR room, for Switch servers with no chat app.

Uses the owner's own gateway session from an agent config (``flip setup`` writes it):

    flip chat --config author-agent.json read             # #pr-<n>, oldest first
    flip chat --config author-agent.json say "Q1: The test kept failing, so ..."
    flip chat --config author-agent.json say --private "@flipside-author-agent offer Q1 step 3"
    flip chat --config author-agent.json cards            # my agent's open approval cards
    flip chat --config author-agent.json show 3f2a        # the exact text a card discloses
    flip chat --config author-agent.json answer 3f2a approve

A message that starts with ``@<agent name>`` tags that agent, as a chat app would.
"""

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any

from flipside.room.daemon import load_config, owner_session
from flipside.room.switch_client import Http, SwitchError, sender_of

PAGE = 200


def room_of(cfg: dict[str, Any], private: bool) -> str:
    if private:
        if cfg["role"] != "author":
            raise SystemExit("only the author has a private room")
        return str(cfg["private"])
    return str(cfg["shared"])


def mention_for(cfg: dict[str, Any], body: str) -> str | None:
    """The agent id a message tags, from its leading ``@name``: the owner's own agent, or
    (for the reviewer) the author's agent."""
    agents = {str(cfg["agent_name"]): str(cfg["agent_id"])}
    if "author_agent_name" in cfg:
        agents[str(cfg["author_agent_name"])] = str(cfg["author_agent"]).removeprefix("agent:")
    for name, agent_id in agents.items():
        if body == f"@{name}" or body.startswith(f"@{name} "):
            return agent_id
    return None


def messages(h: Http, room: str) -> list[dict[str, Any]]:
    """Every message in the room, oldest first."""
    rows: dict[int, dict[str, Any]] = {}
    before: int | None = None
    while True:
        q = f"?limit={PAGE}" + (f"&beforeSeq={before}" if before else "")
        page = h.get(f"/gateway/chats/{room}/messages{q}")
        batch = page.get("messages", []) if isinstance(page, dict) else page
        for m in batch:
            rows[int(m["seq"])] = m
        if not batch or not (isinstance(page, dict) and page.get("hasMore")):
            break
        before = min(int(m["seq"]) for m in batch)
    return [rows[s] for s in sorted(rows)]


def render(m: dict[str, Any]) -> str:
    name = str((m.get("sender") or {}).get("name") or sender_of(m))
    body = str(m.get("body") or "")
    head, *rest = body.split("\n") or [""]
    lines = [f"{int(m['seq']):>4} {name}: {head}", *(f"       {line}" for line in rest)]
    return "\n".join(lines)


def open_cards(h: Http, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Open approval cards of this owner's agent (in the private room, for the author)."""
    rows = h.get("/gateway/agent-sessions/approvals") or []
    return [
        r
        for r in rows
        if r.get("state") == "open"
        and str(r.get("agentId")) == str(cfg["agent_id"])
        and (cfg["role"] != "author" or r.get("roomId") == cfg["private"])
    ]


def find_card(cards: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    hits = [c for c in cards if str(c["requestId"]).startswith(prefix)]
    if len(hits) != 1:
        raise SystemExit(f"{len(hits)} open cards match {prefix!r}; run flip chat cards")
    return hits[0]


def run(cfg: dict[str, Any], a: argparse.Namespace, h: Http) -> int:
    if a.cmd == "read":
        rows = messages(h, room_of(cfg, a.private))
        for m in rows[-a.n :] if a.n else rows:
            print(render(m))
        return 0
    if a.cmd == "say":
        body = " ".join(a.text)
        req: dict[str, Any] = {"requestId": uuid.uuid4().hex, "body": body}
        if (agent := mention_for(cfg, body)) is not None:
            req["mentionAgentId"] = agent
        res = h.post(f"/gateway/chats/{room_of(cfg, a.private)}/messages", req)
        print(f"posted {res['messages'][0]['messageId']}")
        return 0
    cards = open_cards(h, cfg)
    if a.cmd == "cards":
        for c in cards:
            print(f"{str(c['requestId'])[:8]}  {c.get('title', '')}")
        if not cards:
            print("no open cards")
        return 0
    c = find_card(cards, a.card)
    if a.cmd == "show":
        print(c.get("title", ""))
        print()
        print(c.get("detail", ""))
        return 0
    path = (
        f"/gateway/agent-sessions/{c['agentId']}/{c['sessionId']}/approvals/{c['requestId']}/answer"
    )
    h.post(path, {"answer": a.answer})
    print(f"{a.answer}: {c.get('title', '')}")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flip chat", description=__doc__.split("\n\n")[0])
    p.add_argument("--config", type=Path, required=True, help="your agent's config file")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("read", help="print the room")
    r.add_argument("--private", action="store_true", help="the author's private room")
    r.add_argument("-n", type=int, default=0, help="only the last n messages")
    s = sub.add_parser("say", help="post a message")
    s.add_argument("--private", action="store_true", help="the author's private room")
    s.add_argument("text", nargs="+")
    sub.add_parser("cards", help="list your agent's open approval cards")
    sh = sub.add_parser("show", help="print the text an approval card would disclose")
    sh.add_argument("card", help="card id or its first characters")
    an = sub.add_parser("answer", help="answer an approval card")
    an.add_argument("card", help="card id or its first characters")
    an.add_argument("answer", choices=("approve", "decline"))
    return p


def main(argv: list[str]) -> int:
    a = parser().parse_args(argv)
    cfg = load_config(a.config)
    try:
        return run(cfg, a, owner_session(cfg))
    except SwitchError as e:
        print(f"flip chat: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
