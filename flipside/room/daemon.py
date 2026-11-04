"""``flip agent author|reviewer --config FILE``: run one agent as its own long-lived process.

The agent holds its own Switch event stream, reads the room through its owner's gateway
session, and steps once per ``poll`` seconds until SIGTERM or SIGINT. Its state (cards,
dropped requests) and stream cursor live in ``work``, written atomically, so a process
killed at any point restarts without duplicate posts.

The config file holds the agent's API key and points at the owner's credentials file;
it must be mode 0600 and is never printed. Keys:

- common: ``role``, ``base``, ``agent_id``, ``agent_name``, ``api_key``,
  ``owner_creds`` (path) and ``owner_key``, ``session_id``, ``work``, ``shared``, ``repo``,
  ``pr`` (PR data: number, title, body, author, files, checks) or ``github`` (owner/repo)
  with ``pr_number``.
- author: ``private``, ``reviewer_agent``, ``author_user``, ``author_name``; optional
  ``root`` and ``commit`` (default: the newest seal commit in ``base_ref``..HEAD).
- reviewer: ``head``, ``base_ref``, ``author_agent``, ``author_agent_name``, ``pr_author``,
  ``reviewer_name``; optional ``timeout`` (default ``FLIP_ANSWER_TIMEOUT`` or 30 minutes).
"""

import argparse
import datetime as dt
import json
import os
import signal
import stat
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from flipside.room.agents import (
    AuthorAgent,
    AuthorConfig,
    ReviewerAgent,
    ReviewerConfig,
    default_timeout,
    find_seal,
)
from flipside.room.rules import CheckRun, PRData
from flipside.room.switch_client import Http, SwitchError, SwitchTransport
from flipside.room.transport import Forbidden
from flipside.seal.git import parse_trailer, trailer_values


def log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def load_config(path: Path) -> dict[str, Any]:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SystemExit(f"{path} must not be readable by others (mode {mode:o}); chmod 600")
    cfg: dict[str, Any] = json.loads(path.read_text())
    return cfg


def write_config(path: Path, cfg: dict[str, Any]) -> None:
    """Write an agent config readable only by its owner."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, sort_keys=True, indent=1)
    os.chmod(path, 0o600)


def owner_session(cfg: dict[str, Any]) -> Http:
    creds = json.loads(Path(cfg["owner_creds"]).read_text())[cfg["owner_key"]]
    h = Http(cfg["base"])
    h.login(creds["email"], creds["password"])
    return h


def pr_data(cfg: dict[str, Any]) -> PRData:
    if "github" in cfg:
        from flipside.room.github import fetch_pr

        return fetch_pr(cfg["github"], int(cfg["pr_number"]))
    p = cfg["pr"]
    return PRData(
        number=int(p["number"]),
        title=p["title"],
        body=p["body"],
        author=p["author"],
        files=tuple(p["files"]),
        checks=tuple(CheckRun(c["name"], c.get("conclusion")) for c in p.get("checks", [])),
    )


def transport(cfg: dict[str, Any], rooms: tuple[str, ...]) -> SwitchTransport:
    work = Path(cfg["work"])
    return SwitchTransport(
        base=cfg["base"],
        agent_id=cfg["agent_id"],
        api_key=cfg["api_key"],
        name=cfg["agent_name"],
        owner=owner_session(cfg),
        rooms=rooms,
        session_id=cfg["session_id"],
        cursor_path=work / f"{cfg['role']}-cursor.json",
    )


def author(cfg: dict[str, Any]) -> tuple[AuthorAgent, SwitchTransport]:
    repo = Path(cfg["repo"])
    commit, root = cfg.get("commit"), cfg.get("root")
    if not commit:
        commit = find_seal(repo, cfg.get("base_ref", "main"), "HEAD")
        if commit is None:
            raise SystemExit("no Flipside-Seal commit on this branch; run flip seal first")
        trailer = parse_trailer(trailer_values(repo, commit)[0])
        assert trailer is not None
        root = trailer.root
    t = transport(cfg, (cfg["shared"], cfg["private"]))
    agent = AuthorAgent(
        t,
        AuthorConfig(
            pr=int(cfg.get("pr_number") or cfg["pr"]["number"]),
            shared=cfg["shared"],
            private=cfg["private"],
            repo=repo,
            root=root or "",
            commit=commit,
            reviewer_agent=cfg["reviewer_agent"],
            author_user=cfg["author_user"],
            author_name=cfg["author_name"],
            state_path=Path(cfg["work"]) / "author-agent.json",
            agent_name=cfg["agent_name"],
        ),
        log=log,
    )
    return agent, t


def reviewer(cfg: dict[str, Any]) -> tuple[ReviewerAgent, SwitchTransport]:
    t = transport(cfg, (cfg["shared"],))
    timeout = cfg.get("timeout")
    agent = ReviewerAgent(
        t,
        ReviewerConfig(
            pr=pr_data(cfg),
            shared=cfg["shared"],
            repo=Path(cfg["repo"]),
            head=cfg["head"],
            base=cfg["base_ref"],
            author_agent=cfg["author_agent"],
            author_agent_name=cfg["author_agent_name"],
            pr_author=cfg["pr_author"],
            reviewer_name=cfg["reviewer_name"],
            timeout=float(timeout) if timeout is not None else default_timeout(),
        ),
        log=log,
    )
    return agent, t


def run(cfg: dict[str, Any], stop: threading.Event, poll: float = 1.0) -> int:
    """Step the agent until ``stop`` is set. Transient Switch errors are logged and retried."""
    agent: AuthorAgent | ReviewerAgent
    agent, t = author(cfg) if cfg["role"] == "author" else reviewer(cfg)
    log(f"{cfg['agent_name']} started (pid {os.getpid()})")
    try:
        while not stop.is_set():
            try:
                agent.step()
            except (SwitchError, Forbidden, OSError) as e:
                log(f"{cfg['agent_name']} step failed, retrying: {e}")
            except Exception as e:  # keep serving; the run log flags it as a bug
                where = traceback.extract_tb(e.__traceback__)[-1]
                log(
                    f"{cfg['agent_name']} STEP ERROR {type(e).__name__}: {e} "
                    f"({Path(where.filename).name}:{where.lineno})"
                )
            stop.wait(poll)
    finally:
        t.close()
        for note in t.tap.notes:
            log(f"{cfg['agent_name']}: {note}")
        log(f"{cfg['agent_name']} stopped")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="flip agent")
    p.add_argument("role", choices=("author", "reviewer"))
    p.add_argument("--config", required=True, help="agent config file (mode 0600)")
    p.add_argument("--poll", type=float, default=1.0, help="seconds between steps")
    a = p.parse_args(argv)
    cfg = load_config(Path(a.config))
    if cfg.get("role") != a.role:
        raise SystemExit(f"config is for role {cfg.get('role')!r}, not {a.role!r}")
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    return run(cfg, stop, a.poll)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
