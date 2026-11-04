"""Reviewer-side verification (docs/seal/SPEC.md, Verify).

Checks run in order and stop at the first failure:
0 BAD_DISCLOSURE (clarification C4), 1 NO_SEAL, 2 WRONG_COMMIT, 3 NOT_IN_PR,
4 MANIFEST_HASH, 5 MANIFEST_MISMATCH, 6 BAD_SIZE, 7 PROOF_FAIL.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flipside.seal.canon import CanonError, canon
from flipside.seal.git import (
    SealTrailer,
    git_ok,
    parse_trailer,
    resolve_commit,
    trailer_values,
)
from flipside.seal.manifest import LEAF_KEYS, META_KEYS, ManifestError, check_meta, load_manifest
from flipside.seal.merkle import leaf_hash, proof_length, root_from_proof

CODES = (
    "OK",
    "BAD_DISCLOSURE",
    "NO_SEAL",
    "WRONG_COMMIT",
    "NOT_IN_PR",
    "MANIFEST_HASH",
    "MANIFEST_MISMATCH",
    "BAD_SIZE",
    "PROOF_FAIL",
)
EXIT_OK, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DISCLOSURE_KEYS = ("v", "commit", "i", "n", "salt", "leaf", "proof")


@dataclass(frozen=True)
class Verdict:
    """The result of verifying one disclosure."""

    code: str
    detail: str
    i: int | None = None
    leaf: dict[str, Any] | None = None
    root: str | None = None
    commit: str | None = None

    @property
    def ok(self) -> bool:
        return self.code == "OK"

    def message(self) -> str:
        if self.ok and self.leaf is not None and self.root and self.commit:
            lf = self.leaf
            return (
                f"OK leaf {self.i} (session {lf['session']}, step {lf['step']}, "
                f"chunk {lf['chunk']}) against seal {self.root[:7]} in commit "
                f"{self.commit[:7]}"
            )
        return f"{self.code} {self.detail}".rstrip()


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def check_shape(d: Any) -> str | None:
    """Reason a disclosure object is malformed, or None. Extra top-level keys are ignored."""
    if not isinstance(d, dict):
        return "disclosure must be a JSON object"
    missing = [k for k in DISCLOSURE_KEYS if k not in d]
    if missing:
        return f"missing {', '.join(missing)}"
    if d["v"] != 1 or not _is_int(d["v"]):
        return "v must be 1"
    if not isinstance(d["commit"], str) or not HEX40.match(d["commit"]):
        return "commit must be 40 lowercase hex"
    if not _is_int(d["i"]) or d["i"] < 0 or not _is_int(d["n"]) or d["n"] < 0:
        return "i and n must be non-negative integers"
    if not isinstance(d["salt"], str) or not HEX64.match(d["salt"]):
        return "salt must be 64 lowercase hex"
    if not isinstance(d["proof"], list) or not all(
        isinstance(p, str) and HEX64.match(p) for p in d["proof"]
    ):
        return "proof must be a list of 64 lowercase hex"
    leaf = d["leaf"]
    if not isinstance(leaf, dict) or sorted(leaf) != sorted(LEAF_KEYS):
        return "leaf has the wrong keys"
    if not isinstance(leaf["text"], str):
        return "leaf text must be a string"
    reason = check_meta(leaf)
    if reason:
        return f"leaf {reason}"
    try:
        canon(leaf)
    except CanonError as e:
        return f"leaf: {e}"
    return None


def check_against_seal(d: dict[str, Any], manifest: bytes, trailer: SealTrailer) -> Verdict:
    """Checks 4 to 7 against a trailer. Pure: no git. ``d`` must pass check_shape."""
    i, n, leaf = d["i"], d["n"], d["leaf"]
    if hashlib.sha256(manifest).hexdigest() != trailer.manifest:
        return Verdict("MANIFEST_HASH", "manifest SHA-256 differs from the trailer", i)
    try:
        entries = load_manifest(manifest)
    except ManifestError as e:
        return Verdict("MANIFEST_HASH", f"manifest is malformed: {e}", i)
    if i < len(entries):
        want = {k: entries[i][k] for k in META_KEYS}
        got = {k: leaf[k] for k in META_KEYS}
        if want != got:
            diff = sorted(k for k in META_KEYS if want[k] != got[k])
            return Verdict("MANIFEST_MISMATCH", f"leaf {i} differs in {', '.join(diff)}", i)
    if i >= n or n != trailer.n or len(d["proof"]) != proof_length(i, n):
        return Verdict(
            "BAD_SIZE", f"i={i} n={n}, trailer n={trailer.n}, proof length {len(d['proof'])}", i
        )
    lh = leaf_hash(bytes.fromhex(d["salt"]), canon(leaf))
    got_root = root_from_proof(i, n, lh, [bytes.fromhex(p) for p in d["proof"]])
    if got_root is None or got_root.hex() != trailer.root:
        return Verdict("PROOF_FAIL", f"leaf {i} does not hash up to root {trailer.root[:7]}", i)
    return Verdict("OK", "", i, leaf, trailer.root, d["commit"])


def verify(repo: Path, d: Any, manifest: bytes, *, commit: str, head: str = "HEAD") -> Verdict:
    """All checks, in order, for one disclosure against the commit the question named."""
    reason = check_shape(d)
    if reason:
        return Verdict("BAD_DISCLOSURE", reason)
    i = d["i"]
    named = resolve_commit(repo, commit)
    if named is None:
        return Verdict("NO_SEAL", f"commit {commit} is not in this repo", i)
    values = trailer_values(repo, named)
    if len(values) != 1:
        return Verdict("NO_SEAL", f"commit {named[:7]} has {len(values)} Flipside-Seal trailers", i)
    trailer = parse_trailer(values[0])
    if trailer is None:
        return Verdict("NO_SEAL", f"commit {named[:7]} has a malformed Flipside-Seal trailer", i)
    if d["commit"] != named:
        return Verdict(
            "WRONG_COMMIT", f"disclosure names {d['commit'][:7]}, the question named {named[:7]}", i
        )
    head_sha = resolve_commit(repo, head)
    if head_sha is None or not git_ok(repo, "merge-base", "--is-ancestor", named, head_sha):
        return Verdict("NOT_IN_PR", f"{named[:7]} is not in the PR head {head}", i)
    v = check_against_seal(d, manifest, trailer)
    return Verdict(v.code, v.detail, v.i, v.leaf, v.root, named if v.ok else v.commit)
