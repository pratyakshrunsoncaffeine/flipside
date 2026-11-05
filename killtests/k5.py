"""Kill test K5 for Flipside on the demo stack (switch-core 0.31.0 + Mattermost 11.9.0).

K5: in a Mattermost channel bridged to a Switch room, Switch alone decides who a person is.
    Each person types as their own Mattermost account; nothing in the message names them.

    K5.a the author's claimed account tags author-agent: addressed, no refusal.
    K5.b the reviewer's claimed account tags author-agent: not addressed, Switch refuses.
    K5.c an account nobody claimed tags author-agent: not addressed, Switch refuses.
    K5.d the reviewer presses Approve on author-agent's card in Mattermost: no outcome.
    K5.e an account nobody claimed presses Decline on that card: no outcome.
    K5.f the author presses Approve on that card: outcome approve, by the author's account.
    K5.g the reviewer cannot rename the author's private room or rewrite its instructions.
    K5.h the author cannot rewrite the instructions of the reviewer's shared room.

Rooms, agents and policies come from the same bootstrap `make demo` uses, so the policies
under test are the product's. The card sits in the shared room so that every person can
see its buttons. Needs `flip demo up`. Writes evidence/k5-*.log; exit code 0 only if every
check passes. Mattermost passwords stay in .flipside-demo/people.json and are never logged.
"""

from __future__ import annotations

import datetime as dt
import json
import secrets
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flipside.room import demo, solo  # noqa: E402
from flipside.room.agents import AUTHOR_AGENT_NAME  # noqa: E402
from flipside.room.mattermost import MM, MattermostError, card_actions, post_text  # noqa: E402
from flipside.room.protocol import Msg  # noqa: E402
from flipside.room.replay import DEFAULT_CASE  # noqa: E402
from flipside.room.scenario import load_case, materialize  # noqa: E402
from flipside.room.setup import invite  # noqa: E402
from flipside.room.switch_client import Http, SwitchTransport  # noqa: E402
from flipside.room.transport import is_refusal  # noqa: E402

LOG = ROOT / "evidence" / f"k5-{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.log"
STRANGER = "stranger-person"
OUTCOME_WAIT = 12.0
results: list[tuple[str, bool, str]] = []
lines: list[str] = []


def log(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    lines.append(line)


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    log(f"{'PASS' if ok else 'FAIL'} {name} {detail}")


def stranger(conf: dict[str, str]) -> MM:
    """A Mattermost account in the team that no Switch user claimed."""
    path = demo.people_file()
    people: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    p = people.setdefault(
        "stranger", {"mm_user": STRANGER, "mm_password": "Aa1!" + secrets.token_urlsafe(18)}
    )
    demo._private_write(path, json.dumps(people))
    mma = demo.mm_admin(conf)
    team = mma.call("GET", f"/teams/name/{demo.TEAM}")
    try:
        u = mma.call(
            "POST",
            "/users",
            {
                "username": STRANGER,
                "email": f"{STRANGER}@flipside.local",
                "password": p["mm_password"],
                "first_name": "Stranger",
            },
        )
    except MattermostError:
        u = mma.call("GET", f"/users/username/{STRANGER}")
    mma.call("POST", f"/teams/{team['id']}/members", {"team_id": team["id"], "user_id": u["id"]})
    return MM(demo.MM_BASE).login(STRANGER, p["mm_password"])


def find(t: SwitchTransport, room: str, nonce: str, wait: float = 20.0) -> list[Msg]:
    """The room messages that contain ``nonce``, once the tagged one has arrived."""
    deadline = time.monotonic() + wait
    while True:
        hits = [m for m in t.read(room) if nonce in m.body]
        if hits or time.monotonic() > deadline:
            return hits
        time.sleep(1.0)


def tag(who: str, mm: MM, channel: str, t: SwitchTransport, room: str) -> None:
    """``who`` tags author-agent in Mattermost; record Switch's decision and any refusal."""
    nonce = f"k5-{who}-{uuid.uuid4().hex[:8]}"
    mm_name = mm.call("GET", "/users/me")["username"]
    mm.call("POST", "/posts", {"channel_id": channel, "message": f"@{AUTHOR_AGENT_NAME} {nonce}"})
    hits = find(t, room, nonce)
    mine = [m for m in hits if m.body.startswith(f"@{AUTHOR_AGENT_NAME}")]
    if not mine:
        check(f"{who} message reached the room", False, nonce)
        return
    m = mine[0]
    time.sleep(3.0)  # Switch posts its refusal right after the message
    after = [
        x
        for x in t.read(room)
        if x.seq > m.seq and x.sender == t.me and is_refusal(x.body) and f"@{mm_name}" in x.body
    ]
    log(f"{who}: {m.id} sender {m.sender} addressed {m.addressed}; refusals after it {len(after)}")
    for x in after:
        log(f"  refusal {x.id}: {x.body[:120]}")
    expect = who == "author"
    ok = m.addressed is expect and bool(after) is not expect
    name = {"author": "K5.a", "reviewer": "K5.b", "stranger": "K5.c"}[who]
    check(
        f"{name} {who} tags author-agent",
        ok,
        f"addressed={m.addressed} refused={bool(after)} (want addressed={expect})",
    )


def button(mm: MM, channel: str, title: str, name: str, wait: float = 30.0) -> tuple[str, str]:
    deadline = time.monotonic() + wait
    while True:
        page = mm.call("GET", f"/channels/{channel}/posts?per_page=60")
        for pid in page.get("order", []):
            p = page["posts"][pid]
            acts = card_actions(p)
            if name in acts and title in post_text(p):
                return str(pid), acts[name]
        if time.monotonic() > deadline:
            raise MattermostError(f"no {name!r} button for {title!r} in channel {channel}")
        time.sleep(1.5)


def press(who: str, mm: MM, channel: str, title: str, name: str) -> str:
    """``who`` presses ``name`` on the card in Mattermost. Returns what Mattermost said."""
    post, action = button(mm, channel, title, name)
    try:
        res = mm.call("POST", f"/posts/{post}/actions/{action}", {})
        said = json.dumps(res)[:200]
    except MattermostError as e:
        said = str(e)[:200]
    log(f"{who} pressed {name} on post {post}: Mattermost said {said}")
    return said


def refused(h: Http, room: str, body: dict[str, Any]) -> str:
    """'refused' when Switch answers ``h`` changing ``room`` with 403; 'accepted' on success.

    Any other HTTP error (400, 404, 5xx) raises: an outage is not a refusal (Codex review of #33).
    """
    try:
        h.request("PATCH", f"/gateway/rooms/{room}", body)
    except PermissionError as e:
        return f"refused ({type(e).__name__}: {str(e)[:80]})"
    return "accepted"


def outcome(t: SwitchTransport, card: str, wait: float) -> Any:
    deadline = time.monotonic() + wait
    while True:
        got = [o for o in t.outcomes() if o.card == card]
        if got or time.monotonic() > deadline:
            return got[0] if got else None
        time.sleep(1.0)


def main() -> int:
    if not (demo.DIR / "stack.conf").exists():
        log("no demo stack; run `flip demo up` first")
        return 1
    demo.env()
    conf = demo._read_conf(demo.DIR / "stack.conf")
    bridge = demo.wait_ready(conf, timeout=60)
    log(f"cleared {demo.clear_rooms(conf)} review rooms from earlier runs")
    with tempfile.TemporaryDirectory(prefix="flip-k5-") as tmp:
        world = materialize(load_case(DEFAULT_CASE), Path(tmp) / "world")
        live = solo.bootstrap(world, log, "mattermost")
    c = live.cast
    creds = json.loads(demo.people_file().read_text(encoding="utf-8"))
    mm = {
        r: MM(demo.MM_BASE).login(creds[r]["mm_user"], creds[r]["mm_password"]) for r in demo.ROLES
    }
    mm["stranger"] = stranger(conf)
    invite(live.reviewer_h, c.shared, [STRANGER])
    shared = demo.channels(live)[c.shared]
    log(f"Mattermost connection {bridge}; shared room {c.shared} is channel {shared}")
    log(f"{STRANGER} added to the channel; no Switch user claimed it")
    said = refused(live.reviewer_h, c.private, {"name": "renamed", "instructions": "reviewer"})
    check("K5.g reviewer changes the author's private room", said.startswith("refused"), said)
    said = refused(live.author_h, c.shared, {"instructions": "author wrote this"})
    check("K5.h author changes the reviewer's shared room", said.startswith("refused"), said)
    a_id = c.a_agent.split(":", 1)[1]
    with tempfile.TemporaryDirectory(prefix="flip-k5-tap-") as tap:
        t = SwitchTransport(
            base=live.base,
            agent_id=a_id,
            api_key=live.keys["author"],
            name=AUTHOR_AGENT_NAME,
            owner=live.author_h,
            rooms=(c.shared, c.private),
            session_id=live.session_id,
            cursor_path=Path(tap) / "cursor.json",
        )
        try:
            for who in ("author", "reviewer", "stranger"):
                tag(who, mm[who], shared, t, c.shared)
            card = str(uuid.uuid4())
            title = f"K5 card {card[:8]}"
            t.open_card(c.shared, card, title, "Kill test K5: who may answer this card.")
            log(f"author-agent opened card {card} {title!r} in the shared room")
            press("reviewer", mm["reviewer"], shared, title, "Approve")
            o = outcome(t, card, OUTCOME_WAIT)
            check("K5.d reviewer presses Approve: no outcome", o is None, f"outcome={o}")
            press("stranger", mm["stranger"], shared, title, "Decline")
            o = outcome(t, card, OUTCOME_WAIT)
            check("K5.e unclaimed account presses Decline: no outcome", o is None, f"outcome={o}")
            press("author", mm["author"], shared, title, "Approve")
            o = outcome(t, card, OUTCOME_WAIT * 2)
            by = o.answered_by if o else ""
            check(
                "K5.f author presses Approve: outcome approve by the author's account",
                o is not None and o.answer == "approve" and creds["author"]["mm_user"] in by,
                f"outcome={o}",
            )
        finally:
            t.close()
    return finish()


def finish() -> int:
    passed = sum(ok for _, ok, _ in results)
    log(f"K5 {passed}/{len(results)} passed")
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    print(f"evidence {LOG.relative_to(ROOT)}")
    return 0 if results and passed == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # record the failure in the evidence log, then fail
        log(f"ERROR {type(e).__name__}: {e}")
        finish()
        sys.exit(1)
