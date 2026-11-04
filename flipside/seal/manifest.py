"""Leaf objects and the public manifest (docs/seal/SPEC.md, Leaves and Manifest).

This is the manifest loader the room lane imports.
"""

import re
from collections.abc import Sequence
from typing import Any

from flipside.seal.canon import canon
from flipside.seal.steps import Step

LEAF_KEYS = (
    "v",
    "session",
    "step",
    "chunk",
    "role",
    "tools",
    "files",
    "mentions",
    "cmd",
    "ok",
    "text",
)
META_KEYS = tuple(k for k in LEAF_KEYS if k != "text")
ENTRY_KEYS = ("i", *META_KEYS)
ROLES = ("user", "assistant", "tool_result")
CMDS = ("test", "lint", "build", "other")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ManifestError(ValueError):
    """The manifest bytes are not a well-formed v1 manifest."""


def leaf_object(step: Step, chunk: int, text: str) -> dict[str, Any]:
    """The leaf dict that is canonicalised and hashed."""
    return {
        "v": 1,
        "session": step.session,
        "step": step.step,
        "chunk": chunk,
        "role": step.role,
        "tools": list(step.tools),
        "files": list(step.files),
        "mentions": list(step.mentions),
        "cmd": step.cmd,
        "ok": step.ok,
        "text": text,
    }


def manifest_entry(i: int, leaf: dict[str, Any]) -> dict[str, Any]:
    """Manifest entry i: the leaf fields minus text, plus i."""
    return {"i": i, **{k: leaf[k] for k in META_KEYS}}


def manifest_bytes(leaves: Sequence[dict[str, Any]]) -> bytes:
    """canonical_json of every manifest entry, in leaf order. No trailing newline."""
    return canon([manifest_entry(i, leaf) for i, leaf in enumerate(leaves)])


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _str_list(x: object) -> bool:
    return isinstance(x, list) and all(isinstance(s, str) for s in x)


def check_meta(entry: dict[str, Any]) -> str | None:
    """Return a reason when the metadata fields of a leaf or entry are malformed."""
    if entry.get("v") != 1 or not _is_int(entry.get("v")):
        return "v must be 1"
    for k in ("session", "step", "chunk"):
        if not _is_int(entry.get(k)) or entry[k] < 0:
            return f"{k} must be a non-negative integer"
    if entry.get("role") not in ROLES:
        return "bad role"
    for k in ("tools", "files", "mentions"):
        if not _str_list(entry.get(k)):
            return f"{k} must be a list of strings"
    if entry.get("cmd") is not None and entry.get("cmd") not in CMDS:
        return "bad cmd"
    if entry.get("ok") is not None and not isinstance(entry.get("ok"), bool):
        return "ok must be a boolean or null"
    return None


def load_manifest(data: bytes) -> list[dict[str, Any]]:
    """Parse and validate manifest bytes. Raises ManifestError.

    The bytes must be exactly the canonical encoding, so a parsed manifest
    always re-encodes to the bytes whose SHA-256 is in the trailer.
    """
    import json

    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ManifestError(f"manifest is not JSON: {e}") from e
    if not isinstance(obj, list) or not obj:
        raise ManifestError("manifest must be a non-empty list")
    for i, entry in enumerate(obj):
        if not isinstance(entry, dict) or sorted(entry) != sorted(ENTRY_KEYS):
            raise ManifestError(f"entry {i} has the wrong keys")
        if entry["i"] != i or not _is_int(entry["i"]):
            raise ManifestError(f"entry {i} has i={entry['i']!r}")
        reason = check_meta(entry)
        if reason:
            raise ManifestError(f"entry {i}: {reason}")
    try:
        if canon(obj) != data:
            raise ManifestError("manifest bytes are not canonical JSON")
    except ValueError as e:
        raise ManifestError(str(e)) from e
    return obj
