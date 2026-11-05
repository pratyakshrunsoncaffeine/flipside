"""``flip solo``: one machine, two owners, the full flow on a real local Switch server.

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
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flipside.room.agents import AUTHOR_AGENT_NAME, REVIEWER_AGENT_NAME
from flipside.room.daemon import write_config
from flipside.room.protocol import accept
from flipside.room.replay import DEFAULT_CASE, ROOT, case_timeout, report
from flipside.room.run import Card, Cast, Humans, Log, Result, Script, play
from flipside.room.scenario import World, load_case, materialize
from flipside.room.setup import (
    OWNER_RULE,
    bridged_ids,
    invite,
    linked_names,
    open_room,
    policy,
    private_greeting,
    register,
    shared_greeting,
)
from flipside.room.setup import bridge as find_bridge
from flipside.room.switch_client import DEFAULT_BASE, Http, SwitchTransport

CREDS = ROOT / "killtests" / ".local-users.json"
APPS = ("slack", "mattermost")
CONSOLE_ENV = (
    Path.home()
    / "Library/Application Support/switchdash/local-switch-server/native/run/switch-core.env"
)


def base_url() -> str:
    return os.environ.get("SWITCH_BASE", DEFAULT_BASE)


def creds_path() -> Path:
    """The local users' passwords (mode 0600). ``FLIP_USERS_FILE`` overrides it, so a second
    Switch server (``flip demo``) keeps its own users apart from the Console server's."""
    return Path(os.environ.get("FLIP_USERS_FILE", str(CREDS)))


def admin_login(base: str) -> Http:
    path = Path(os.environ.get("FLIP_SWITCH_ENV", str(CONSOLE_ENV)))
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
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
    path = creds_path()
    creds = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    existing = {u["email"] for u in admin.get("/gateway/users")}
    if role not in creds:
        email = f"{role}@flipside.local"
        if email in existing:
            raise SystemExit(
                f"{email} already exists on this Switch server, but {path} has no password "
                "for it; copy that file (mode 0600) from the clone that created the user"
            )
        creds[role] = {
            "email": email,
            "password": secrets.token_urlsafe(18),
            "name": role.capitalize(),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        write_config(path, creds)  # created 0600: the passwords are never world-readable
    c = creds[role]
    if c["email"] not in existing:
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
    author_answerers: list[str] = field(default_factory=list)


def bootstrap(world: World, log: Log, app: str | None = None) -> Live:
    """Users, agents, rooms and policies for one run. Fresh rooms every run. With ``app``
    ("slack" or "mattermost") both rooms are private channels on the server's connection to
    that messaging app, and each person's linked account is added to the channels they are in."""
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
    bridge = find_bridge(admin, app) if app else None
    n = world.pr.number
    shared = open_room(reviewer_h, f"pr-{n}", r_agent, shared_greeting(n), bridge)
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
    private = open_room(author_h, f"pr-{n}-author", a_agent, private_greeting(n), bridge)
    answerers: list[str] = []
    if bridge:
        answerers = bridged_ids(author_h, bridge, app or "slack")
        author_names = linked_names(author_h, bridge)
        invite(reviewer_h, shared, linked_names(reviewer_h, bridge) + author_names)
        invite(author_h, private, author_names)
        log(f"{app} connection {bridge}: added linked accounts {author_names or 'none'} (author)")
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
    return Live(base, author_h, reviewer_h, keys, cast, str(uuid.uuid4()), answerers)


def agent_configs(world: World, live: Live, work: Path) -> dict[str, Path]:
    """Write both agents' config files (mode 0600) and return their paths."""
    c = live.cast
    common = {
        "base": live.base,
        "owner_creds": str(creds_path()),
        "work": str(work),
        "shared": c.shared,
    }
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
            "author_answerers": live.author_answerers,
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

    def stop_file(self, role: str) -> Path:
        return self.work / f"{role}-agent.stop"

    def start(self, role: str) -> None:
        cmd = [sys.executable, "-m", "flipside.cli", "agent", role]
        self.stop_file(role).unlink(missing_ok=True)
        with (self.work / f"{role}-agent.log").open("ab") as out:
            self.procs[role] = subprocess.Popen(
                [
                    *cmd,
                    "--config",
                    str(self.configs[role]),
                    "--stop-file",
                    str(self.stop_file(role)),
                ],
                stdout=out,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
        self.log(f"{role}-agent process started (pid {self.procs[role].pid})")

    def kill(self, role: str) -> None:
        p = self.procs[role]
        p.kill()  # SIGKILL on POSIX, TerminateProcess on Windows: no cleanup either way
        p.wait(10)
        self.log(f"restart: {role}-agent process killed with SIGKILL (pid {p.pid})")

    def stop_all(self) -> None:
        """Ask every agent to stop through its stop file, so its shutdown runs on every OS."""
        for role in self.procs:
            self.stop_file(role).touch()
        for role, p in self.procs.items():
            if p.poll() is None:
                try:
                    p.wait(15)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(5)
            self.log(f"{role}-agent process exited with {p.returncode}")

    def output(self, role: str) -> list[str]:
        path = self.work / f"{role}-agent.log"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def run_switch(
    world: World,
    log: Log,
    work: Path,
    restarts: bool = True,
    app: str | None = None,
    press: bool = False,
    pace: float = 1.0,
    people: Callable[[Live, Log], Humans] | None = None,
) -> Result:
    """Play ``world`` on the local Switch server with each agent in its own process;
    with ``app`` the rooms are channels in that messaging app (see ``bootstrap``). With
    ``press`` the author answers their cards in the app, and the run waits up to 15 minutes
    for it; ``pace`` is the pause between the people's turns, in seconds. ``people`` builds
    the two humans for the run (default: both act through the gateway); people who type in
    the messaging app answer questions through author-agent."""
    live = bootstrap(world, log, app)
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
    humans: Humans = people(live, log) if people else SwitchHumans(owners, ids, c.private, log)
    script = Script(world, humans, c, attack["author"], attack["reviewer"], AUTHOR_AGENT_NAME, log)
    script.by_hand = press
    if people:
        script.answer_prefix = f"@{AUTHOR_AGENT_NAME} "
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
        return (
            list(json.loads(state.read_text(encoding="utf-8")).get("dropped", []))
            if state.exists()
            else []
        )

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
            max_rounds=max(90, int(900 / (2 * pace))) if press else 90,
            pause=pace,
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


def run_case(
    case_dir: Path,
    restarts: bool,
    app: str | None = None,
    press: bool = False,
    pace: float = 1.0,
    people: Callable[[Live, Log], Humans] | None = None,
    prefix: str = "solo",
) -> tuple[bool, str]:
    """Run one case live; write ``evidence/<prefix>-<case>-<time>.log``. Returns the result
    and the log name."""
    case = load_case(case_dir)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_path = ROOT / "evidence" / f"{prefix}-{case.name}-{stamp}.log"
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
        result = run_switch(
            world, log, work, restarts=restarts, app=app, press=press, pace=pace, people=people
        )
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
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    print(f"evidence {log_path.relative_to(ROOT)}")
    return ok, log_path.name


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="flip solo")
    p.add_argument("--case", default=str(DEFAULT_CASE))
    p.add_argument("--all", action="store_true", help="run every case in fixtures/cases")
    p.add_argument("--no-restart", action="store_true", help="skip the restart test")
    p.add_argument(
        "--slack",
        action="store_const",
        const="slack",
        dest="app",
        help="open the rooms as Slack channels on the server's Slack connection",
    )
    p.add_argument(
        "--mattermost",
        action="store_const",
        const="mattermost",
        dest="app",
        help="open the rooms as Mattermost channels on the server's Mattermost connection",
    )
    p.add_argument(
        "--press",
        action="store_true",
        help="with --slack or --mattermost: leave the author's cards for the author to answer",
    )
    p.add_argument("--pace", type=float, default=1.0, help="seconds between the people's turns")
    a = p.parse_args(argv)
    if a.press and not a.app:
        p.error("--press needs --slack or --mattermost")
    if not a.all:
        return 0 if run_case(Path(a.case), not a.no_restart, a.app, a.press, a.pace)[0] else 1
    rows = []
    for d in sorted((ROOT / "fixtures" / "cases").iterdir()):
        ok, name = run_case(d, not a.no_restart, a.app, a.press, a.pace)
        rows.append(f"{'PASS' if ok else 'FAIL'} {d.name} evidence/{name}")
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    summary = ROOT / "evidence" / f"solo-all-{stamp}.log"
    passed = sum(r.startswith("PASS") for r in rows)
    summary.write_text(
        "\n".join([*rows, f"RESULT {passed}/{len(rows)} cases pass live"]) + "\n",
        encoding="utf-8",
        newline="",
    )
    print(summary.read_text(encoding="utf-8"), end="")
    return 0 if passed == len(rows) else 1
