"""``flip solo``: one machine, two owners, the full flow on a real local Switch server (M3).

Reuses (or creates) the two local users Author and Reviewer, registers each one's agent,
opens the reviewer-owned shared room and the author's private room, and sets both agents'
scoped policies. Each agent then runs as its own process (``flip agent``), exactly as an
author or reviewer would run it. The two people act only through the gateway calls a chat
client makes: post, list their own approval cards, answer one.

Restart test: author-agent is killed with SIGKILL while its first card is pending, and
reviewer-agent while its first request is unanswered; both are started again from their
state and stream cursor. The run fails if any agent post repeats.

Credentials: the Switch admin login is read from the Console env file (``FLIP_SWITCH_ENV``
overrides the path); the users' generated passwords live in ``killtests/.local-users.json``
and the agents' API keys in per-run config files, all mode 0600. None is printed or logged.
"""

import argparse
import datetime as dt
import json
import os
import secrets
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flipside.room.agents import AUTHOR_AGENT_NAME, REVIEWER_AGENT_NAME
from flipside.room.daemon import write_config
from flipside.room.protocol import accept
from flipside.room.replay import DEFAULT_CASE, ROOT, case_timeout, report
from flipside.room.run import Card, Cast, Log, Result, Script, play
from flipside.room.scenario import World, load_case, materialize
from flipside.room.setup import OWNER_RULE, policy, register, room_id
from flipside.room.switch_client import DEFAULT_BASE, Http, SwitchTransport

CREDS = ROOT / "killtests" / ".local-users.json"
CONSOLE_ENV = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/run/switch-core.env"
)


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


@dataclass
class SwitchHumans:
    """The two people, acting through the gateway only."""

    users: dict[str, Http]
    agents: dict[str, str]
    private: str
    log: Log
    seen: dict[str, tuple[str, str]] = field(default_factory=dict)

    def say(self, who: str, room: str, body: str, mention_agent: str | None = None) -> str:
        req: dict[str, Any] = {"requestId": uuid.uuid4().hex, "body": body}
        if mention_agent:
            req["mentionAgentId"] = self.agents[mention_agent]
        res = self.users[who].post(f"/gateway/chats/{room}/messages", req)
        mid = str(res["messages"][0]["messageId"])
        self.log(f"{who} posted {mid}: {body.splitlines()[0][:80]}")
        return mid

    def pending_cards(self, who: str) -> list[Card]:
        """Open cards of the person's own agents in this run's private room."""
        out = []
        for row in self.users[who].get("/gateway/agent-sessions/approvals") or []:
            if row.get("roomId") != self.private or row.get("state") != "open":
                continue
            self.seen[str(row["requestId"])] = (str(row["agentId"]), str(row["sessionId"]))
            out.append(Card(str(row["requestId"]), str(row["title"])))
        return out

    def answer_card(self, who: str, card: str, answer: str) -> None:
        agent, session = self.seen[card]
        path = f"/gateway/agent-sessions/{agent}/{session}/approvals/{card}/answer"
        self.users[who].post(path, {"answer": answer})
        self.log(f"{who} answered card {card[:8]}: {answer}")


@dataclass
class Live:
    """One run's Switch setup: sessions, agents and rooms."""

    base: str
    author_h: Http
    reviewer_h: Http
    keys: dict[str, str]
    cast: Cast
    session_id: str


def bootstrap(world: World, log: Log) -> Live:
    """Users, agents, rooms and policies for one run. Fresh rooms every run."""
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
    # Switch matches a person against `users` by their member client id, which the gateway
    # does not expose, so reviewer-agent admits any person in its own #pr-<n> room: only
    # the author and the reviewer are members, and it acts only on the PR author's answers.
    reviewer_h.put(
        f"/gateway/agents/{r_agent}/addressing-policy",
        policy(OWNER_RULE, {"rooms": [shared], "users": "*", "agents": [a_agent]}),
    )
    author_h.put(
        f"/gateway/agents/{a_agent}/addressing-policy",
        policy(OWNER_RULE, {"rooms": [shared], "users": [], "agents": [r_agent]}),
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
    keys = {"author": a_key, "reviewer": r_key}
    return Live(base, author_h, reviewer_h, keys, cast, str(uuid.uuid4()))


def agent_configs(world: World, live: Live, work: Path) -> dict[str, Path]:
    """Write both agents' config files (mode 0600) and return their paths."""
    c = live.cast
    common = {"base": live.base, "owner_creds": str(CREDS), "work": str(work), "shared": c.shared}
    pr = world.pr
    cfgs: dict[str, dict[str, Any]] = {
        "author": {
            **common,
            "role": "author",
            "agent_id": c.a_agent.split(":", 1)[1],
            "agent_name": AUTHOR_AGENT_NAME,
            "api_key": live.keys["author"],
            "owner_key": "author",
            "session_id": live.session_id,
            "private": c.private,
            "repo": str(world.author_repo),
            "root": world.root,
            "commit": world.commit,
            "pr_number": pr.number,
            "reviewer_agent": c.r_agent,
            "author_user": c.author_u,
            "author_name": c.author_name,
        },
        "reviewer": {
            **common,
            "role": "reviewer",
            "agent_id": c.r_agent.split(":", 1)[1],
            "agent_name": REVIEWER_AGENT_NAME,
            "api_key": live.keys["reviewer"],
            "owner_key": "reviewer",
            "session_id": str(uuid.uuid4()),
            "repo": str(world.reviewer_repo),
            "head": world.head,
            "base_ref": world.base,
            "pr": {
                "number": pr.number,
                "title": pr.title,
                "body": pr.body,
                "author": pr.author,
                "files": list(pr.files),
                "checks": [{"name": k.name, "conclusion": k.conclusion} for k in pr.checks],
            },
            "author_agent": c.a_agent,
            "author_agent_name": AUTHOR_AGENT_NAME,
            "pr_author": c.author_u,
            "reviewer_name": c.reviewer_name,
            "timeout": case_timeout(world),
        },
    }
    paths = {}
    for role, cfg in cfgs.items():
        paths[role] = work / f"{role}-agent.config.json"
        write_config(paths[role], cfg)
    return paths


@dataclass
class Agents:
    """The two agent processes, each writing to its own log file."""

    configs: dict[str, Path]
    work: Path
    log: Log
    procs: dict[str, subprocess.Popen[bytes]] = field(default_factory=dict)

    def start(self, role: str) -> None:
        cmd = [sys.executable, "-m", "flipside.cli", "agent", role]
        with (self.work / f"{role}-agent.log").open("ab") as out:
            self.procs[role] = subprocess.Popen(
                [*cmd, "--config", str(self.configs[role])],
                stdout=out,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        self.log(f"{role}-agent process started (pid {self.procs[role].pid})")

    def kill(self, role: str) -> None:
        p = self.procs[role]
        p.send_signal(signal.SIGKILL)
        p.wait(10)
        self.log(f"restart: {role}-agent process killed with SIGKILL (pid {p.pid})")

    def stop_all(self) -> None:
        for role, p in self.procs.items():
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(15)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(5)
            self.log(f"{role}-agent process exited with {p.returncode}")

    def output(self, role: str) -> list[str]:
        path = self.work / f"{role}-agent.log"
        return path.read_text().splitlines() if path.exists() else []


def run_switch(world: World, log: Log, work: Path, restarts: bool = True) -> Result:
    """Play ``world`` on the local Switch server with each agent in its own process."""
    live = bootstrap(world, log)
    c = live.cast
    agents = Agents(agent_configs(world, live, work), work, log)
    ids = {"author": c.a_agent.split(":", 1)[1], "reviewer": c.r_agent.split(":", 1)[1]}
    names = {"author": AUTHOR_AGENT_NAME, "reviewer": REVIEWER_AGENT_NAME}
    owners = {"author": live.author_h, "reviewer": live.reviewer_h}
    attack = {
        role: SwitchTransport(
            base=live.base,
            agent_id=ids[role],
            api_key=live.keys[role],
            name=names[role],
            owner=owners[role],
            rooms=(c.shared,),
            session_id=live.session_id,
            cursor_path=work / f"attack-{role}-cursor.json",
            listen=False,
        )
        for role in ("author", "reviewer")
    }
    humans = SwitchHumans(owners, ids, c.private, log)
    script = Script(world, humans, c, attack["author"], attack["reviewer"], AUTHOR_AGENT_NAME, log)
    killed: set[str] = set()

    def on_round(_rnd: int, transcript: list[Any]) -> None:
        if not restarts:
            return
        if "author" not in killed and "author" in agents.procs and humans.pending_cards("author"):
            killed.add("author")
            agents.kill("author")
            agents.start("author")
        mine = [o for m in transcript if (o := accept(m, c.roles)) and m.sender == c.r_agent]
        requested = any(o["t"] == "request" for o in mine)
        verdict = any(o["t"] == "verdict" for o in mine)
        if "reviewer" not in killed and requested and not verdict:
            killed.add("reviewer")
            agents.kill("reviewer")
            agents.start("reviewer")

    def dropped() -> list[str]:
        state = work / "author-agent.json"
        return list(json.loads(state.read_text()).get("dropped", [])) if state.exists() else []

    if world.commit:
        agents.start("author")
    else:
        log("no seal commit: author-agent is not started (the UNSEALED path)")
    agents.start("reviewer")
    try:
        result = play(
            world,
            script,
            lambda: attack["author"].read(c.shared),
            log,
            dropped=dropped,
            max_rounds=90,
            pause=1.0,
            on_round=on_round,
            settle=4,
        )
    finally:
        agents.stop_all()
        for role in ("author", "reviewer"):
            for line in agents.output(role):
                log(f"[{role}-agent] {line}")
    log(f"Switch message ids: {', '.join(r['id'] for r in result.transcript)}")
    return result


def run_case(case_dir: Path, restarts: bool) -> tuple[bool, str]:
    """Run one case live; write its evidence log. Returns the result and the log name."""
    case = load_case(case_dir)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = ROOT / "evidence" / f"solo-{case.name}-{stamp}.log"
    lines: list[str] = []

    def log(msg: str) -> None:
        line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        lines.append(line)

    with tempfile.TemporaryDirectory(prefix="flip-solo-") as tmp:
        work = Path(tmp)
        world = materialize(case, work / "world")
        log(
            f"case {case.name}: PR #{world.pr.number} {world.pr.title!r}; seal commit "
            f"{world.commit or 'none'}"
        )
        started = time.monotonic()
        result = run_switch(world, log, work, restarts=restarts)
        log(f"elapsed {time.monotonic() - started:.0f} s")
        diffs = report(result, case.expected, log)
    dups = result.summary()["duplicates"]
    log(f"duplicate agent posts: {len(dups)}" + (f" {dups}" if dups else ""))
    r = result.refusals
    four = all((r.switch_refusal, r.dropped_request, r.forged_verdict, r.card_403))
    attacks = bool(case.raw.get("refusals"))
    if attacks:
        log(f"four refusals live: {'yes' if four else 'NO'}")
    restarted = sum("process killed with SIGKILL" in x for x in lines)
    log(f"agent processes killed and restarted: {restarted}")
    errors = [x for x in lines if "STEP ERROR" in x or "Traceback" in x]
    log(f"agent step errors: {len(errors)}")
    ok = (
        not diffs and not dups and not errors and (four or not attacks) and result.brief is not None
    )
    log(f"RESULT {'PASS' if ok else 'FAIL'} {case.name} (switch, {result.rounds} rounds)")
    log_path.parent.mkdir(exist_ok=True)
    log_path.write_text("\n".join(lines) + "\n")
    print(f"evidence {log_path.relative_to(ROOT)}")
    return ok, log_path.name


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="flip solo")
    p.add_argument("--case", default=str(DEFAULT_CASE))
    p.add_argument("--all", action="store_true", help="run every case in fixtures/cases")
    p.add_argument("--no-restart", action="store_true", help="skip the restart test")
    a = p.parse_args(argv)
    if not a.all:
        return 0 if run_case(Path(a.case), not a.no_restart)[0] else 1
    rows = []
    for d in sorted((ROOT / "fixtures" / "cases").iterdir()):
        ok, name = run_case(d, not a.no_restart)
        rows.append(f"{'PASS' if ok else 'FAIL'} {d.name} evidence/{name}")
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    summary = ROOT / "evidence" / f"solo-all-{stamp}.log"
    passed = sum(r.startswith("PASS") for r in rows)
    summary.write_text("\n".join([*rows, f"RESULT {passed}/{len(rows)} cases pass live"]) + "\n")
    print(summary.read_text(), end="")
    return 0 if passed == len(rows) else 1
