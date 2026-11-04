"""``flip solo``: one machine, two owners, the full flow on a real local Switch server (M3).

Creates (or reuses) the two local users Author and Reviewer, registers
each one's agent, opens the reviewer-owned shared room and the author's private room, sets
author-agent's scoped policy, and plays the case with ``SwitchTransport``. Both people act
only through the gateway calls a chat client makes. Midway, each agent is stopped and
restarted from its state and stream cursor; the run fails if any agent post repeats.

Credentials: the Switch admin login is read from the Console env file (``FLIP_SWITCH_ENV``
overrides the path); the two users' generated passwords live in
``killtests/.local-users.json`` (mode 0600). Neither is ever printed or logged.
"""

import argparse
import datetime as dt
import json
import os
import secrets
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flipside.room.agents import AuthorAgent, ReviewerAgent
from flipside.room.replay import (
    AUTHOR_AGENT_NAME,
    DEFAULT_CASE,
    REVIEWER_AGENT_NAME,
    ROOT,
    Cast,
    author_agent,
    idle_without_seal,
    report,
    reviewer_agent,
)
from flipside.room.run import Log, Result, Script, play
from flipside.room.scenario import World, load_case, materialize
from flipside.room.switch_client import DEFAULT_BASE, Http, SwitchTransport

CREDS = ROOT / "killtests" / ".local-users.json"
CONSOLE_ENV = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/run/switch-core.env"
)
RESTART_AUTHOR_AT, RESTART_REVIEWER_AT = 3, 2


def base_url() -> str:
    return os.environ.get("SWITCH_BASE", DEFAULT_BASE)


def admin_login(base: str) -> Http:
    path = Path(os.environ.get("FLIP_SWITCH_ENV", str(CONSOLE_ENV)))
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    admin = Http(base)
    admin.login(env["GATEWAY_ADMIN_EMAIL"], env["GATEWAY_ADMIN_PASSWORD"])
    return admin


def person(admin: Http, base: str, role: str) -> tuple[Http, str, str]:
    """The local user for ``role`` ("author" or "reviewer"), created on first use.

    Agent names are unique on a Switch server, so the same two users own the two agents in
    the kill tests and in every solo run. Returns the session, the user id and the name."""
    creds = json.loads(CREDS.read_text()) if CREDS.exists() else {}
    if role not in creds:
        creds[role] = {
            "email": f"{role}@flipside.local",
            "password": secrets.token_urlsafe(18),
            "name": role.capitalize(),
        }
        CREDS.write_text(json.dumps(creds))
        os.chmod(CREDS, 0o600)
    c = creds[role]
    if c["email"] not in {u["email"] for u in admin.get("/gateway/users")}:
        admin.post(
            "/gateway/users",
            {"name": c["name"], "email": c["email"], "password": c["password"], "role": "member"},
        )
    user = Http(base)
    user.login(c["email"], c["password"])
    return user, str(user.get("/gateway/auth/me")["id"]), str(c["name"])


def register(user: Http, base: str, name: str) -> tuple[str, str]:
    """Register (or re-key) the user's agent called ``name``. Returns its id and API key."""
    key = user.post("/gateway/api-keys", {"label": f"flipside-{name}"})
    token = key.get("key") or key.get("api_key") or key.get("token") or key.get("secret")
    if not token and key.get("id"):
        token = user.get(f"/gateway/api-keys/{key['id']}/reveal").get("key")
    res = Http(base, bearer=token).post(
        "/agents/register-known",
        {
            "agent_type": "codex",
            "name": name,
            "description": f"Flipside {name}",
            "options": {},
            "overwrite": True,
        },
    )
    return str(res["id"]), str(res["api_key"])


def room_id(chat: dict[str, Any]) -> str:
    c = chat.get("chat", chat)
    return str(c.get("roomId") or c.get("room_id") or c.get("id"))


@dataclass
class SwitchHumans:
    """The two people, acting through the gateway only."""

    users: dict[str, Http]
    agents: dict[str, str]
    author_agent: str
    session_id: str
    log: Log

    def say(self, who: str, room: str, body: str, mention_agent: str | None = None) -> str:
        req: dict[str, Any] = {"requestId": uuid.uuid4().hex, "body": body}
        if mention_agent:
            req["mentionAgentId"] = self.agents[mention_agent]
        res = self.users[who].post(f"/gateway/chats/{room}/messages", req)
        mid = str(res["messages"][0]["messageId"])
        self.log(f"{who} posted {mid}: {body.splitlines()[0][:80]}")
        return mid

    def answer_card(self, who: str, card: str, answer: str) -> None:
        path = (
            f"/gateway/agent-sessions/{self.author_agent}/{self.session_id}/approvals/{card}/answer"
        )
        self.users[who].post(path, {"answer": answer})
        self.log(f"{who} answered card {card[:8]}: {answer}")


def run_switch(world: World, log: Log, work: Path, restarts: bool = True) -> Result:
    """Play ``world`` on the local Switch server. Fresh rooms and a fresh agent session per run."""
    base = base_url()
    admin = admin_login(base)
    author_h, author_id, author_name = person(admin, base, "author")
    reviewer_h, reviewer_id, reviewer_name = person(admin, base, "reviewer")
    a_agent, a_key = register(author_h, base, AUTHOR_AGENT_NAME)
    r_agent, r_key = register(reviewer_h, base, REVIEWER_AGENT_NAME)
    log(
        f"Switch {base}: author {author_name} user {author_id}, reviewer {reviewer_name} user "
        f"{reviewer_id}; author-agent {a_agent}, reviewer-agent {r_agent}"
    )

    n = world.pr.number
    shared = room_id(
        reviewer_h.post(
            "/gateway/chats",
            {"requestId": uuid.uuid4().hex, "name": f"pr-{n}", "agentIds": [r_agent]},
        )
    )
    # Switch matches a human against `users` by their member client id, which the gateway
    # does not expose, so reviewer-agent admits any human in its own #pr-<n> room: only the
    # author and the reviewer are members, and it acts only on the PR author's answers.
    reviewer_h.put(
        f"/gateway/agents/{r_agent}/addressing-policy",
        {
            "policy": {
                "rules": [
                    {"users": [], "agents": [], "owner": True, "owner_agents": True},
                    {"rooms": [shared], "users": "*", "agents": [a_agent]},
                ]
            }
        },
    )
    author_h.put(
        f"/gateway/agents/{a_agent}/addressing-policy",
        {
            "policy": {
                "rules": [
                    {"users": [], "agents": [], "owner": True, "owner_agents": True},
                    {"rooms": [shared], "users": [], "agents": [r_agent]},
                ]
            }
        },
    )
    reviewer_h.post(f"/gateway/chats/{shared}/members", {"userId": author_id})
    reviewer_h.post(f"/gateway/rooms/{shared}/agents", {"agent_ids": [a_agent]})
    private = room_id(
        author_h.post(
            "/gateway/chats",
            {"requestId": uuid.uuid4().hex, "name": f"pr-{n}-author", "agentIds": [a_agent]},
        )
    )
    log(
        f"reviewer opened #pr-{n} {shared} and added the author and author-agent; author opened "
        f"#pr-{n}-author {private}; author-agent policy: owner, owner's agents, reviewer-agent "
        f"in #pr-{n} only; reviewer-agent policy: owner, owner's agents, author-agent and the "
        f"room's people in #pr-{n}"
    )

    sid = str(uuid.uuid4())
    cast = Cast(
        f"user:{author_id}",
        f"user:{reviewer_id}",
        f"agent:{a_agent}",
        f"agent:{r_agent}",
        shared,
        private,
        author_name,
        reviewer_name,
    )

    def a_transport() -> SwitchTransport:
        return SwitchTransport(
            base=base,
            agent_id=a_agent,
            api_key=a_key,
            name=AUTHOR_AGENT_NAME,
            owner=author_h,
            rooms=(shared, private),
            session_id=sid,
            cursor_path=work / "author-cursor.json",
        )

    def r_transport() -> SwitchTransport:
        return SwitchTransport(
            base=base,
            agent_id=r_agent,
            api_key=r_key,
            name=REVIEWER_AGENT_NAME,
            owner=reviewer_h,
            rooms=(shared,),
            session_id=str(uuid.uuid4()),
            cursor_path=work / "reviewer-cursor.json",
        )

    live: dict[str, SwitchTransport] = {"author": a_transport(), "reviewer": r_transport()}
    author = idle_without_seal(world, author_agent(world, live["author"], cast, work, log))
    reviewer = reviewer_agent(world, live["reviewer"], cast, log, time.monotonic)
    humans = SwitchHumans(
        {"author": author_h, "reviewer": reviewer_h},
        {"author": a_agent, "reviewer": r_agent},
        a_agent,
        sid,
        log,
    )
    script = Script(
        world,
        humans,
        author,
        reviewer,
        live["author"],
        live["reviewer"],
        shared,
        AUTHOR_AGENT_NAME,
        log,
    )

    def restart(rnd: int, a: AuthorAgent, r: ReviewerAgent) -> tuple[AuthorAgent, ReviewerAgent]:
        if not restarts:
            return a, r
        if rnd == RESTART_AUTHOR_AT:
            live["author"].close()
            live["author"] = a_transport()
            a = idle_without_seal(world, author_agent(world, live["author"], cast, work, log))
            script.author_t = live["author"]
            log(f"restart: author-agent stopped and restarted before round {rnd}")
        if rnd == RESTART_REVIEWER_AT:
            live["reviewer"].close()
            live["reviewer"] = r_transport()
            r = reviewer_agent(world, live["reviewer"], cast, log, time.monotonic)
            script.reviewer_t = live["reviewer"]
            log(f"restart: reviewer-agent stopped and restarted before round {rnd}")
        return a, r

    try:
        result = play(
            world,
            author,
            reviewer,
            script,
            lambda: live["author"].read(shared),
            log,
            max_rounds=40,
            pause=1.0,
            restart=restart,
        )
    finally:
        for t in live.values():
            t.close()
            for note in t.tap.notes:
                log(f"{t.name}: {note}")
    log(f"Switch message ids: {', '.join(r['id'] for r in result.transcript)}")
    return result


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="flip solo")
    p.add_argument("--case", default=str(DEFAULT_CASE))
    p.add_argument("--no-restart", action="store_true", help="skip the restart test")
    a = p.parse_args(argv)
    case = load_case(Path(a.case))
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = ROOT / "evidence" / f"solo-{case.name}-{stamp}.log"
    lines: list[str] = []

    def log(msg: str) -> None:
        line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line)
        lines.append(line)

    with tempfile.TemporaryDirectory(prefix="flip-solo-") as tmp:
        work = Path(tmp)
        world = materialize(case, work / "world")
        log(
            f"case {case.name}: PR #{world.pr.number} {world.pr.title!r}; seal commit "
            f"{world.commit or 'none'}"
        )
        result = run_switch(world, log, work, restarts=not a.no_restart)
        diffs = report(result, case.expected, log)
    dups = result.summary()["duplicates"]
    log(f"duplicate agent posts: {len(dups)}" + (f" {dups}" if dups else ""))
    r = result.refusals
    four = all((r.switch_refusal, r.dropped_request, r.forged_verdict, r.card_403))
    log(f"four refusals live: {'yes' if four else 'NO'}")
    ok = not diffs and not dups and four and result.brief is not None
    log(f"RESULT {'PASS' if ok else 'FAIL'} {case.name} (switch, {result.rounds} rounds)")
    log_path.parent.mkdir(exist_ok=True)
    log_path.write_text("\n".join(lines) + "\n")
    print(f"evidence {log_path.relative_to(ROOT)}")
    return 0 if ok else 1
