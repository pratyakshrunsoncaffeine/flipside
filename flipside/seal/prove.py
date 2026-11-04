"""Author-side disclosure (docs/seal/SPEC.md, Prove).

Rebuilds the sealed leaves from local state after the F1 prefix check, then
returns the disclosure for one leaf.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flipside.seal.merkle import inclusion_proof
from flipside.seal.seal import Sealed, Source, build_leaves, load_key, parse_sources, state_dir
from flipside.seal.secrets import Hit, overlapping, scan


class ProveError(RuntimeError):
    """A disclosure cannot be made. ``code`` is SESSION_CHANGED, NO_STATE or BAD_LEAF."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass(frozen=True)
class Rebuilt:
    """The sealed leaves rebuilt from local state."""

    state: dict[str, Any]
    sealed: Sealed


def load_state(repo: Path, root: str) -> dict[str, Any]:
    path = state_dir(repo) / f"{root}.json"
    try:
        state: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ProveError("NO_STATE", f"no local seal state for root {root[:12]}") from e
    return state


def _prefix(record: dict[str, Any]) -> bytes:
    path, length = Path(record["path"]), int(record["length"])
    try:
        with path.open("rb") as fh:
            data = fh.read(length)
    except OSError as e:
        raise ProveError("SESSION_CHANGED", f"{path.name} cannot be read") from e
    if len(data) != length or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ProveError("SESSION_CHANGED", f"the sealed part of {path.name} changed")
    return data


def rebuild(repo: Path, root: str) -> Rebuilt:
    """Re-read each session's sealed prefix (F1), check it, and rebuild every leaf.

    Bytes appended after the seal are ignored. Raises ProveError(SESSION_CHANGED)
    when a sealed prefix or a stored tool-results file differs.
    """
    state = load_state(repo, root)
    sources = [Source(Path(r["path"]), _prefix(r)) for r in state["sessions"]]
    for r in state["aux"]:
        _prefix(r)
    key = load_key(state_dir(repo) / f"{root}.key")
    sealed = build_leaves(parse_sources(sources, Path(state["repo"]), state["changed_files"]), key)
    if sealed.root.hex() != root:
        raise ProveError("SESSION_CHANGED", "rebuilt root differs from the seal")
    return Rebuilt(state, sealed)


def disclosure(rebuilt: Rebuilt, i: int, commit: str | None = None) -> dict[str, Any]:
    """The disclosure object for leaf i (SPEC Prove)."""
    sealed = rebuilt.sealed
    if not 0 <= i < sealed.n:
        raise ProveError("BAD_LEAF", f"leaf {i} is outside 0..{sealed.n - 1}")
    sha = commit or rebuilt.state.get("commit")
    if not sha:
        raise ProveError("NO_STATE", "the seal has no commit; pass --commit")
    return {
        "v": 1,
        "commit": sha,
        "i": i,
        "n": sealed.n,
        "salt": sealed.salts[i].hex(),
        "leaf": sealed.leaves[i],
        "proof": [h.hex() for h in inclusion_proof(i, sealed.hashes)],
    }


def prove(repo: Path, root: str, i: int, commit: str | None = None) -> dict[str, Any]:
    """``flip prove --root <hex> --leaf <i>``: check, rebuild, and disclose leaf i."""
    return disclosure(rebuild(repo, root), i, commit)


def leaf_secret_hits(rebuilt: Rebuilt, i: int) -> list[Hit]:
    """Secret hits that overlap leaf i, scanning its whole step so split secrets are caught."""
    leaf = rebuilt.sealed.leaves[i]
    same = [
        lf
        for lf in rebuilt.sealed.leaves
        if lf["session"] == leaf["session"] and lf["step"] == leaf["step"]
    ]
    step_text = "".join(lf["text"] for lf in same)
    start = sum(len(lf["text"]) for lf in same[: leaf["chunk"]])
    return overlapping(scan(step_text), start, start + len(leaf["text"]))
