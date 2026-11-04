"""Kill test K3 for Flipside: the approval card in Slack, answerable only by the author.

Needs a Slack connection on the local Switch server (Switch Console, Messaging apps) and the
author's Slack account linked to author@flipside.local ("This is me").

K3.a the author's private room is bridged to a Slack channel.
K3.b author-agent's approval card renders in that channel with Approve and Decline buttons.
K3.c the reviewer cannot answer the card.
K3.d the author answers it by pressing a button in Slack, and author-agent receives that answer.

Environment:
  SLACK_BOT_TOKEN_FILE  file holding the Slack bot token (xoxb-), read to check the channel.
  K3_WAIT_SECONDS       how long to wait for the button press (default 600).

Writes an evidence log to ../evidence/. Exit code 0 only if every check passes.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid

from k1_k2 import open_stream, register, users
from switch_api import BASE, Client, HTTPError, console_env, rid

HERE = pathlib.Path(__file__).parent
EVIDENCE = HERE.parent / "evidence"
EVIDENCE.mkdir(exist_ok=True)
LOG = EVIDENCE / f"k3-{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.log"
results: list[tuple[str, bool, str]] = []


def log(msg: str) -> None:
    line = f"{dt.datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8", newline="") as f:
        f.write(line + "\n")


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")


def slack(token: str, method: str, **params: str) -> dict:
    """One Slack Web API call with the bot token. Never logs the token."""
    url = f"https://slack.com/api/{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def buttons(message: dict) -> list[str]:
    """Labels of the buttons in a Slack message's blocks."""
    out = []
    for block in message.get("blocks") or []:
        for el in block.get("elements") or []:
            if el.get("type") == "button":
                out.append(str((el.get("text") or {}).get("text", "")))
        acc = block.get("accessory") or {}
        if acc.get("type") == "button":
            out.append(str((acc.get("text") or {}).get("text", "")))
    return out


def finish() -> int:
    passed = bool(results) and all(ok for _, ok, _ in results)
    n_ok = sum(ok for _, ok, _ in results)
    log(f"RESULT {'PASS' if passed else 'FAIL'} ({n_ok}/{len(results)}); log {LOG}")
    return 0 if passed else 1


def main() -> int:
    token_file = os.environ.get("SLACK_BOT_TOKEN_FILE")
    if not token_file:
        sys.exit("Set SLACK_BOT_TOKEN_FILE to a file holding the Slack bot token (xoxb-).")
    bot = pathlib.Path(token_file).expanduser().read_text(encoding="utf-8").strip()
    wait_s = int(os.environ.get("K3_WAIT_SECONDS", "600"))

    env = console_env()
    admin = Client()
    admin.login(env["GATEWAY_ADMIN_EMAIL"], env["GATEWAY_ADMIN_PASSWORD"])
    creds = users(admin)
    author, reviewer = Client(), Client()
    author.login(creds["author"]["email"], creds["author"]["password"])
    reviewer.login(creds["reviewer"]["email"], creds["reviewer"]["password"])
    author_id = author.call("GET", "/gateway/auth/me")["id"]
    log(f"server {BASE}; author user {author_id}")

    bridges = [
        b
        for b in admin.call("GET", "/gateway/collaborations") or []
        if b.get("bridge_type") == "slack" and b.get("status") == "active"
    ]
    if not bridges:
        check("K3.a a Slack connection is active on the Switch server", False, "none")
        return finish()
    bridge = bridges[0]
    bid = bridge["bridge_id"]
    linked = admin.call("GET", f"/gateway/collaborations/{bid}/users") or []
    claimed = [
        u for u in linked if any(c.get("user_id") == author_id for c in u.get("claimed_by") or [])
    ]
    author_slack = [u["external_user_id"] for u in claimed]
    # Switch reports a Slack button press as the bridged identity of the Slack user who pressed
    # it, "@switch-slack-<connection id>-<slack username>:<server>", not as "user:<switch id>".
    author_bridged = [f"@switch-slack-{bid}-{u['external_username']}:" for u in claimed]
    log(f"Slack connection {bridge.get('display_name')} {bid}; author's Slack ids {author_slack}")
    if not author_slack:
        sys.exit("Link the author's Slack account first (Switch Console: This is me).")
    team = slack(bot, "auth.test")
    log(f"Slack bot {team.get('user')} in workspace {team.get('team')} {team.get('team_id')}")

    a_agent, a_key = register(author, "flipside-author-agent")
    log(f"author-agent {a_agent}")

    stamp = dt.datetime.now().strftime("%m%d%H%M%S")
    name = f"pr-k3-{stamp}-author"
    room = author.call(
        "POST",
        "/gateway/rooms",
        {
            "name": name,
            "description": "Flipside approvals: only the author and author-agent are here.",
            "agent_ids": [a_agent],
            "bridge_id": bid,
            "channel_type": "channel_private",
        },
    )
    room_id = room.get("id") or room.get("room_id")
    detail = author.call("GET", f"/gateway/rooms/{room_id}")
    channel = detail.get("external_channel_id")
    log(
        f"room {name} {room_id}: bridge {detail.get('bridge_type')}, channel {channel}, "
        f"url {detail.get('external_channel_url')}"
    )
    check(
        "K3.a the author's private room is bridged to a Slack channel",
        detail.get("bridge_id") == bid and bool(channel),
        f"channel {channel}",
    )
    if not channel:
        return finish()
    for uid in author_slack:
        res = slack(bot, "conversations.invite", channel=channel, users=uid)
        log(f"invite author {uid} to {channel}: ok={res.get('ok')} {res.get('error') or ''}")

    # A live event stream plus heartbeats on the same connection id, as `flip agent` keeps.
    # Without it Switch renders the card as "Host offline" with no buttons.
    stop = threading.Event()
    open_stream(a_agent, a_key, room_id, stop)
    agent = Client(bearer=a_key)
    sid = str(uuid.uuid4())
    try:
        agent.call("POST", f"/agent-sessions/{sid}/started", {"start_source": "room"})
    except HTTPError as e:
        log(f"session started report: {e}")
    disclosure = "Q1: step 7: 'pytest tests/test_report.py -q -> 3 passed' (synthetic K3 card)"
    req_id = rid()
    agent.call(
        "POST",
        f"/agent-sessions/{sid}/approvals",
        {
            "request_id": req_id,
            "turn_id": req_id,
            "kind": "approval",
            "title": "Disclose step 7 to reviewer-agent?",
            "detail": disclosure,
            "options": [
                {"id": "approve", "label": "Approve", "decision": "accept"},
                {"id": "decline", "label": "Decline", "decision": "decline"},
            ],
            "questions": [],
            "room_id": room_id,
            "thread_id": None,
            "expires_at": None,
        },
    )
    log(f"author-agent opened card {req_id} in {name}")

    card: dict = {}
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not card:
        hist = slack(bot, "conversations.history", channel=channel, limit="20")
        for m in hist.get("messages") or []:
            if buttons(m):
                card = m
                break
        if not card:
            time.sleep(2)
    labels = buttons(card)
    log(f"Slack card ts {card.get('ts')}: text {str(card.get('text'))[:160]!r}; buttons {labels}")
    check(
        "K3.b the approval card renders in Slack with Approve and Decline buttons",
        any("approve" in b.lower() for b in labels) and any("decline" in b.lower() for b in labels),
        f"buttons {labels}",
    )

    path = f"/gateway/agent-sessions/{a_agent}/{sid}/approvals/{req_id}/answer"
    try:
        reviewer.call("POST", path, {"answer": "approve"})
        check("K3.c the reviewer cannot answer the card", False, "reviewer answer accepted")
    except HTTPError as e:
        check(
            "K3.c the reviewer cannot answer the card",
            e.status in (401, 403, 404, 409),
            f"{e.status} {e.body[:160]}",
        )

    log(f"WAITING up to {wait_s}s: press Approve on the card in Slack channel #{name}")
    mine: list[dict] = []
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline and not mine:
        outcomes = agent.call("GET", "/agent-sessions/approvals/outcomes") or []
        mine = [o for o in outcomes if o.get("requestId") == req_id and o.get("answer")]
        if not mine:
            time.sleep(2)
    got = mine[0] if mine else {}
    log(f"outcome {json.dumps(got)[:300]}")
    by = str(got.get("answeredBy") or "")
    check(
        "K3.d the author's button press in Slack reaches author-agent",
        got.get("answer") == "approve" and any(by.startswith(p) for p in author_bridged),
        f"answer {got.get('answer')}, answeredBy {by} (author's Slack identities {author_bridged})",
    )
    stop.set()
    return finish()


if __name__ == "__main__":
    sys.exit(main())
