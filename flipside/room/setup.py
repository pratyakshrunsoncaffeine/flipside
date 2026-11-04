"""``flip setup``: connect a real PR's two owners and their agents on a Switch server.

Each owner runs it on their own machine with their own Switch login. The two sides swap
one join line each (by any channel), so neither ever sees the other's credentials:

1. Author:   ``flip setup author --pr 142 --repo . --creds me.json --as me``
   registers author-agent, opens the private room ``#pr-142-author`` and prints line A.
2. Reviewer: ``flip setup reviewer --join "<line A>" --github acme/shop --pr 142 --repo .
   --creds me.json --as me`` registers reviewer-agent, opens ``#pr-142`` with it, sets its
   policy, adds the author and author-agent, writes its config and prints line B.
3. Author:   ``flip setup author --join "<line B>" --out author-agent.json`` sets
   author-agent's policy (owner, owner's agents, reviewer-agent in ``#pr-142`` only) and
   completes its config.

Then each side runs ``flip agent <role> --config <file>``. The creds file holds
``{"<key>": {"email": ..., "password": ...}}``, mode 0600; config files are written 0600
and hold the agent's API key. Nothing secret is printed.
"""

import argparse
import json
import os
import shlex
import stat
import sys
import uuid
from pathlib import Path
from typing import Any

from flipside.room.agents import AUTHOR_AGENT_NAME, REVIEWER_AGENT_NAME
from flipside.room.daemon import check_config, write_config
from flipside.room.switch_client import DEFAULT_BASE, Http, SwitchError

OWNER_RULE = {"users": [], "agents": [], "owner": True, "owner_agents": True}
JOIN = "flip-join"
JOIN_VERSION = "v1"


class SetupError(ValueError):
    """Bad input to ``flip setup``."""


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


def policy(*rules: dict[str, Any]) -> dict[str, Any]:
    return {"policy": {"rules": list(rules)}}


def open_chat(user: Http, name: str, agent_id: str) -> str:
    return room_id(
        user.post(
            "/gateway/chats", {"requestId": uuid.uuid4().hex, "name": name, "agentIds": [agent_id]}
        )
    )


def author_policy(shared: str, reviewer_agent: str) -> dict[str, Any]:
    """author-agent: its owner and owner's agents anywhere; reviewer-agent in ``#pr-<n>`` only."""
    return policy(OWNER_RULE, {"rooms": [shared], "users": [], "agents": [reviewer_agent]})


def reviewer_policy(shared: str, author_agent: str) -> dict[str, Any]:
    """reviewer-agent: its owner and owner's agents; author-agent and the room's people in
    ``#pr-<n>``. Switch matches people by a member client id the gateway does not expose, so
    ``users`` is ``*`` in that one room; reviewer-agent acts only on the PR author's sender id."""
    return policy(OWNER_RULE, {"rooms": [shared], "users": "*", "agents": [author_agent]})


def join_line(**fields: Any) -> str:
    return " ".join(
        [JOIN, JOIN_VERSION, *(f"{k}={shlex.quote(str(v))}" for k, v in fields.items())]
    )


def parse_join(line: str, role: str) -> dict[str, str]:
    """The fields of a join line printed by the other side; ``role`` is that side's role."""
    words = shlex.split(line.strip())
    if words[:2] != [JOIN, JOIN_VERSION]:
        raise SetupError(f"not a {JOIN} {JOIN_VERSION} line")
    out = {}
    for w in words[2:]:
        k, sep, v = w.partition("=")
        if not sep:
            raise SetupError(f"bad join field {w!r}")
        out[k] = v
    if out.get("role") != role:
        raise SetupError(f"expected the {role}'s join line, got role {out.get('role')!r}")
    return out


def load_creds(path: Path, key: str) -> dict[str, str]:
    """One owner's Switch login. On POSIX the file must be mode 0600; Windows has no mode
    bits (access is by ACL), so the check applies only where the mode means something."""
    mode = stat.S_IMODE(path.stat().st_mode)
    if os.name == "posix" and mode & 0o077:
        raise SetupError(f"{path} must not be readable by others (mode {mode:o}); chmod 600")
    creds = json.loads(path.read_text(encoding="utf-8"))
    if key not in creds:
        raise SetupError(f"{path} has no entry {key!r}")
    c: dict[str, str] = creds[key]
    return c


def login(base: str, creds: Path, key: str) -> tuple[Http, str, str]:
    """The owner's gateway session, user id and display name."""
    c = load_creds(creds, key)
    h = Http(base)
    h.login(c["email"], c["password"])
    me = h.get("/gateway/auth/me")
    return h, str(me["id"]), str(c.get("name") or me.get("name") or c["email"].split("@")[0])


def setup_author_start(a: argparse.Namespace, owner: tuple[Http, str, str]) -> str:
    """Step 1: register author-agent, open the private room, write a partial config.
    ``owner`` is the author's gateway session, user id and name (``login``)."""
    h, uid, name = owner
    agent, key = register(h, a.base, a.agent_name)
    private = open_chat(h, f"pr-{a.pr}-author", agent)
    repo = Path(a.repo).resolve()
    cfg = {
        "role": "author",
        "base": a.base,
        "agent_id": agent,
        "agent_name": a.agent_name,
        "api_key": key,
        "owner_creds": str(Path(a.creds).resolve()),
        "owner_key": a.as_,
        "session_id": str(uuid.uuid4()),
        "work": str(
            Path(a.work).resolve() if a.work else repo / ".git" / "flipside" / "work-author"
        ),
        "repo": str(repo),
        "base_ref": a.base_ref,
        "pr_number": a.pr,
        "private": private,
        "author_user": f"user:{uid}",
        "author_name": name,
    }
    write_config(Path(a.out), cfg)
    return join_line(
        role="author", pr=a.pr, user=uid, name=name, agent=agent, agent_name=a.agent_name
    )


def setup_author_finish(a: argparse.Namespace, http: Http | None = None) -> str:
    """Step 3: set author-agent's policy from the reviewer's join line, complete the config."""
    j = parse_join(a.join, "reviewer")
    out = Path(a.out)
    cfg = json.loads(out.read_text(encoding="utf-8"))
    if int(j["pr"]) != int(cfg["pr_number"]):
        raise SetupError(f"join line is for PR #{j['pr']}, config is for PR #{cfg['pr_number']}")
    h = http or login(cfg["base"], Path(cfg["owner_creds"]), cfg["owner_key"])[0]
    h.put(
        f"/gateway/agents/{cfg['agent_id']}/addressing-policy", author_policy(j["room"], j["agent"])
    )
    cfg["shared"] = j["room"]
    cfg["reviewer_agent"] = f"agent:{j['agent']}"
    check_config(cfg)
    write_config(out, cfg)
    return f"author-agent ready; run: flip agent author --config {out}"


def pr_source(a: argparse.Namespace) -> dict[str, Any]:
    """Where reviewer-agent reads the PR: GitHub (``--github``), or a PR data file
    (``--pr-json``, keys number, title, body, author, files, checks, and optionally
    changed_lines for the SIZE gap) with ``--head``."""
    if bool(a.github) == bool(a.pr_json):
        raise SetupError("give exactly one of --github or --pr-json")
    if a.github:
        return {"github": a.github, **({"head": a.head} if a.head else {})}
    if not a.head:
        raise SetupError("--pr-json needs --head (the PR head commit)")
    pr = json.loads(Path(a.pr_json).read_text(encoding="utf-8"))
    missing = [k for k in ("number", "title", "body", "author", "files") if k not in pr]
    if missing:
        raise SetupError(f"{a.pr_json} is missing: {', '.join(missing)}")
    if int(pr["number"]) != a.pr:
        raise SetupError(f"{a.pr_json} is PR #{pr['number']}, not #{a.pr}")
    return {"pr": pr, "head": a.head}


def setup_reviewer(a: argparse.Namespace, owner: tuple[Http, str, str]) -> str:
    """Step 2: register reviewer-agent, open ``#pr-<n>``, admit the author and author-agent."""
    j = parse_join(a.join, "author")
    if int(j["pr"]) != a.pr:
        raise SetupError(f"join line is for PR #{j['pr']}, not #{a.pr}")
    source = pr_source(a)
    h, _uid, name = owner
    agent, key = register(h, a.base, a.agent_name)
    shared = open_chat(h, f"pr-{a.pr}", agent)
    h.put(f"/gateway/agents/{agent}/addressing-policy", reviewer_policy(shared, j["agent"]))
    h.post(f"/gateway/chats/{shared}/members", {"userId": j["user"]})
    h.post(f"/gateway/rooms/{shared}/agents", {"agent_ids": [j["agent"]]})
    repo = Path(a.repo).resolve()
    cfg: dict[str, Any] = {
        "role": "reviewer",
        "base": a.base,
        "agent_id": agent,
        "agent_name": a.agent_name,
        "api_key": key,
        "owner_creds": str(Path(a.creds).resolve()),
        "owner_key": a.as_,
        "session_id": str(uuid.uuid4()),
        "work": str(
            Path(a.work).resolve() if a.work else repo / ".git" / "flipside" / "work-reviewer"
        ),
        "repo": str(repo),
        "base_ref": a.base_ref,
        "shared": shared,
        **source,
        "pr_number": a.pr,
        "author_agent": f"agent:{j['agent']}",
        "author_agent_name": j["agent_name"],
        "pr_author": f"user:{j['user']}",
        "reviewer_name": name,
    }
    check_config(cfg)
    write_config(Path(a.out), cfg)
    line = join_line(role="reviewer", pr=a.pr, room=shared, agent=agent, agent_name=a.agent_name)
    return f"{line}\nreviewer-agent ready; run: flip agent reviewer --config {a.out}"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flip setup", description=__doc__.split("\n\n")[0])
    p.add_argument("role", choices=("author", "reviewer"))
    p.add_argument("--join", help="the other side's join line (author step 3, reviewer)")
    p.add_argument("--pr", type=int, help="pull request number")
    p.add_argument("--repo", default=".", help="local clone of the repo (default .)")
    p.add_argument("--github", help="owner/repo on GitHub (reviewer)")
    p.add_argument("--pr-json", help="PR data file instead of GitHub (reviewer)")
    p.add_argument("--head", help="PR head commit (default: from GitHub)")
    p.add_argument("--creds", type=Path, help="owner credentials file (mode 0600)")
    p.add_argument("--as", dest="as_", help="entry in the credentials file")
    p.add_argument("--base", default=os.environ.get("SWITCH_BASE", DEFAULT_BASE), help="Switch URL")
    p.add_argument("--base-ref", default="origin/main", help="the PR's base branch")
    p.add_argument("--agent-name", help="agent name (unique on the server)")
    p.add_argument("--work", help="agent state directory (default .git/flipside/work-<role>)")
    p.add_argument("--out", help="config file to write (default <role>-agent.json)")
    return p


def main(argv: list[str]) -> int:
    a = parser().parse_args(argv)
    a.out = a.out or f"{a.role}-agent.json"
    a.agent_name = a.agent_name or (
        AUTHOR_AGENT_NAME if a.role == "author" else REVIEWER_AGENT_NAME
    )
    finishing = a.role == "author" and a.join
    if not finishing:
        missing = [f for f in ("pr", "creds", "as_") if getattr(a, f) is None]
        if a.role == "reviewer" and not (a.github or a.pr_json):
            missing.append("github or --pr-json")
        if a.role == "reviewer" and not a.join:
            missing.append("join")
        if missing:
            flags = ", ".join("--" + m.rstrip("_").replace("_", "-") for m in missing)
            print(f"flip setup {a.role}: missing {flags}", file=sys.stderr)
            return 1
    try:
        if a.role == "reviewer":
            print(setup_reviewer(a, login(a.base, a.creds, a.as_)))
        elif finishing:
            print(setup_author_finish(a))
        else:
            print(setup_author_start(a, login(a.base, a.creds, a.as_)))
            print(
                "send this line to the reviewer; then run flip setup author --join '<their line>'"
            )
    except (SetupError, SwitchError, OSError, KeyError) as e:
        print(f"flip setup {a.role}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
