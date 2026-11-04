"""Seal a Claude Code session (docs/seal/SPEC.md, Sessions to Seal record).

Builds the salted leaves, the RFC 9162 root and the public manifest, writes
the key and local state under ``.git/flipside/``, and adds the empty seal commit.
"""

import hashlib
import hmac
import json
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flipside.seal.canon import canon
from flipside.seal.git import (
    TRAILER_KEY,
    GitError,
    SealTrailer,
    changed_files,
    common_dir,
    git,
    resolve_commit,
    toplevel,
)
from flipside.seal.manifest import leaf_object, manifest_bytes
from flipside.seal.merkle import leaf_hash, mth
from flipside.seal.steps import Step, chunks, first_timestamp, parse_session, sealed_prefix

SALT_TAG = b"flipside/salt/v1"
KEY_BYTES = 32
STATE_VERSION = 1
COMMIT_SUBJECT = "flipside: seal session"


class SealError(RuntimeError):
    """Sealing cannot proceed (empty session, staged changes, bad key, ...)."""


@dataclass(frozen=True)
class Sealed:
    """Every leaf of one seal, with salts and hashes. Private: never leaves the author."""

    leaves: list[dict[str, Any]]
    salts: list[bytes]
    hashes: list[bytes]
    root: bytes
    manifest: bytes

    @property
    def n(self) -> int:
        return len(self.leaves)

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(self.manifest).hexdigest()

    @property
    def trailer(self) -> SealTrailer:
        return SealTrailer(self.root.hex(), self.n, self.manifest_sha256)


@dataclass(frozen=True)
class Source:
    """One session file and its sealed prefix."""

    path: Path
    data: bytes


def salt_for(key: bytes, session: int, step: int, chunk: int) -> bytes:
    """salt = HMAC-SHA256(K, "flipside/salt/v1" || canonical_json([session, step, chunk]))."""
    return hmac.new(key, SALT_TAG + canon([session, step, chunk]), hashlib.sha256).digest()


def build_leaves(steps: Sequence[Step], key: bytes) -> Sealed:
    """Chunk every step, salt and hash every leaf, and build the root and manifest."""
    if len(key) != KEY_BYTES:
        raise SealError("the seal key must be 32 bytes")
    ordered = sorted(steps, key=lambda s: (s.session, s.step))
    leaves: list[dict[str, Any]] = []
    for s in ordered:
        for c, text in enumerate(chunks(s.text)):
            leaves.append(leaf_object(s, c, text))
    if not leaves:
        raise SealError("EMPTY_SESSION: the session has no user or assistant steps")
    salts = [salt_for(key, lf["session"], lf["step"], lf["chunk"]) for lf in leaves]
    hashes = [leaf_hash(salt, canon(lf)) for salt, lf in zip(salts, leaves, strict=True)]
    return Sealed(leaves, salts, hashes, mth(hashes), manifest_bytes(leaves))


def session_files(main: Path) -> list[Path]:
    """Session 0 is the main JSONL; 1..k are subagent transcripts (F3).

    Subagents are ``<session-id>/subagents/agent-*.jsonl``, sorted by the
    timestamp of their first line, then by file name.
    """
    sub_dir = main.with_suffix("") / "subagents"
    subs = sorted(sub_dir.glob("agent-*.jsonl")) if sub_dir.is_dir() else []
    keyed = [(first_timestamp(sealed_prefix(p.read_bytes())), p.name, p) for p in subs]
    return [main, *[p for _, _, p in sorted(keyed)]]


def tool_results_dir(main: Path) -> Path:
    return main.with_suffix("") / "tool-results"


def parse_sources(
    sources: Sequence[Source],
    repo_root: Path,
    changed: Sequence[str],
    aux_reads: dict[str, bytes] | None = None,
) -> list[Step]:
    """Parse every session prefix into steps (session index = position in ``sources``)."""
    tr = str(tool_results_dir(sources[0].path))
    steps: list[Step] = []
    for idx, src in enumerate(sources):
        steps.extend(
            parse_session(
                src.data,
                idx,
                repo_root=str(repo_root),
                changed_files=changed,
                main=idx == 0,
                tool_results_dir=tr,
                aux_reads=aux_reads,
            )
        )
    return steps


def read_sources(paths: Sequence[Path]) -> list[Source]:
    """Read each file and cut it at its last complete line."""
    return [Source(p, sealed_prefix(p.read_bytes())) for p in paths]


def project_dir_name(path: Path) -> str:
    """Claude Code's project folder name: every non-alphanumeric character becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def projects_root() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".claude") / "projects"


def latest_session(repo_root: Path) -> Path:
    """The most recently modified session JSONL for this repo's Claude Code project folder."""
    d = projects_root() / project_dir_name(repo_root)
    found = sorted(d.glob("*.jsonl"), key=lambda p: (p.stat().st_mtime, p.name))
    if not found:
        raise SealError(f"no Claude Code session found in {d}; pass --session")
    return found[-1]


def state_dir(repo: Path) -> Path:
    return common_dir(repo) / "flipside"


def _write_private(path: Path, data: bytes) -> None:
    """Write ``data`` byte for byte to a file only its owner can read.

    ``O_BINARY`` matters on Windows: without it the C runtime turns each LF byte of a
    random key into CR LF, and ``load_key`` then refuses the key."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def load_key(path: Path) -> bytes:
    key = path.read_bytes()
    if len(key) != KEY_BYTES:
        raise SealError(f"{path} does not hold a 32-byte key")
    return key


@dataclass(frozen=True)
class SealResult:
    """What ``flip seal`` produced."""

    sealed: Sealed
    commit: str | None
    state_path: Path
    manifest_path: Path
    key_path: Path


def _file_record(path: Path, data: bytes) -> dict[str, Any]:
    return {"path": str(path), "length": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def seal(
    repo: Path,
    session: Path,
    base: str,
    *,
    key: bytes | None = None,
    commit: bool = True,
    amend: bool = False,
) -> SealResult:
    """Seal ``session`` for the PR from ``base`` to HEAD in ``repo``.

    Writes ``.git/flipside/<root>.key`` (0600), ``<root>.json`` (local state) and
    ``<root>.manifest.json``; then, unless ``commit`` is False, adds the empty
    seal commit (or amends HEAD when ``amend`` is set and HEAD is unpushed).
    """
    repo = toplevel(repo)
    if commit and git(repo, "diff", "--cached", "--name-only").strip():
        raise SealError("staged changes would go into the seal commit; commit them first")
    if amend and git(repo, "branch", "-r", "--contains", "HEAD").strip():
        raise SealError("--amend is only for an unpushed branch; HEAD is on a remote")
    try:
        changed = changed_files(repo, base)
    except GitError as e:
        raise SealError(f"cannot diff against base {base!r}: {e}") from e
    key = key if key is not None else os.urandom(KEY_BYTES)
    sources = read_sources(session_files(session))
    aux: dict[str, bytes] = {}
    sealed = build_leaves(parse_sources(sources, repo, changed, aux), key)
    root = sealed.root.hex()

    sdir = state_dir(repo)
    sdir.mkdir(mode=0o700, parents=True, exist_ok=True)
    key_path = sdir / f"{root}.key"
    _write_private(key_path, key)
    manifest_path = sdir / f"{root}.manifest.json"
    manifest_path.write_bytes(sealed.manifest)

    sha: str | None = None
    if commit:
        trailer = f"{TRAILER_KEY}: {sealed.trailer.line()}"
        if amend:
            git(repo, "commit", "--amend", "--no-edit", "--allow-empty", "--trailer", trailer)
        else:
            git(repo, "commit", "--allow-empty", "-m", COMMIT_SUBJECT, "--trailer", trailer)
        sha = resolve_commit(repo, "HEAD")

    state = {
        "v": STATE_VERSION,
        "root": root,
        "n": sealed.n,
        "manifest": sealed.manifest_sha256,
        "commit": sha,
        "repo": str(repo),
        "base": base,
        "changed_files": changed,
        "sessions": [_file_record(s.path, s.data) for s in sources],
        "aux": [_file_record(Path(p), d) for p, d in sorted(aux.items())],
    }
    state_path = sdir / f"{root}.json"
    _write_private(state_path, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode())
    return SealResult(sealed, sha, state_path, manifest_path, key_path)
