"""Loads the author's agent sessions for a PR from Entire checkpoints in the local repo.

Entire keeps checkpoints on the `entire/checkpoints/v1` branch, sharded as
`<id[:2]>/<id[2:]>/<session index>/full.jsonl`, with sessions numbered from 0 and long
transcripts split into `full.jsonl`, `full.jsonl.001`, `full.jsonl.002`, ...
(entireio/cli checkpoint/persistent.go and agent/chunking.go).
With `entire configure --skip-push-sessions` that branch exists only on the author's
machine, which is why the gate runs there.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from ownership_gate.transcript import Session, Step, parse_claude_code

log = logging.getLogger("ownership_gate")
CHECKPOINT_BRANCHES = ("entire/checkpoints/v1", "origin/entire/checkpoints/v1")
TRANSCRIPT = "full.jsonl"
MAX_SESSIONS_PER_CHECKPOINT = 50
MAX_CHUNKS = 999
GIT_TIMEOUT_SECONDS = 30


def load_session(repo_dir: Path, checkpoint_ids: Iterable[str]) -> Session | None:
    """Join every session of every checkpoint into one numbered session, or None if none."""
    ids = list(checkpoint_ids)
    transcripts = [t for cid in ids for t in _transcripts(repo_dir, cid)]
    if not transcripts:
        if ids:
            log.warning(
                "PR has Entire-Checkpoint trailers %s but no local checkpoint data in %s",
                ", ".join(ids),
                repo_dir,
            )
        return None
    return join_sessions(parse_claude_code(t.splitlines()) for t in transcripts)


def load_transcript_file(path: Path) -> Session:
    return parse_claude_code(path.read_text(encoding="utf-8").splitlines())


def join_sessions(sessions: Iterable[Session]) -> Session:
    steps: list[Step] = []
    for session in sessions:
        steps += [replace(s, index=len(steps) + i) for i, s in enumerate(session.steps, 1)]
    return Session(steps=tuple(steps))


def _transcripts(repo_dir: Path, checkpoint_id: str) -> list[str]:
    shard = f"{checkpoint_id[:2]}/{checkpoint_id[2:]}"
    for branch in CHECKPOINT_BRANCHES:
        found = []
        for n in range(MAX_SESSIONS_PER_CHECKPOINT):
            text = _session_transcript(repo_dir, f"{branch}:{shard}/{n}")
            if text is None:
                break
            found.append(text)
        if found:
            return found
    return []


def _session_transcript(repo_dir: Path, session_spec: str) -> str | None:
    first = _git_show(repo_dir, f"{session_spec}/{TRANSCRIPT}")
    if first is None:
        return None
    chunks = [first]
    for i in range(1, MAX_CHUNKS + 1):
        chunk = _git_show(repo_dir, f"{session_spec}/{TRANSCRIPT}.{i:03d}")
        if chunk is None:
            break
        chunks.append(chunk)
    return "".join(c if c.endswith("\n") else c + "\n" for c in chunks)


def _git_show(repo_dir: Path, spec: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "show", spec],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as err:
        log.error("could not run git to read %s: %s", spec, err)
        return None
    return result.stdout if result.returncode == 0 else None
