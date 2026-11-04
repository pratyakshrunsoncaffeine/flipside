"""Canonical JSON for leaves and the manifest (docs/seal/SPEC.md, Leaves).

Keys sorted, separators "," and ":" with no spaces, UTF-8, ensure_ascii off.
Allowed values: str, int, bool, None, list, dict with str keys. Floats raise.
"""

import json
import math
from typing import Any


class CanonError(ValueError):
    """A value cannot be encoded as canonical JSON."""


def _check(obj: Any, allow_float: bool) -> None:
    if obj is None or isinstance(obj, (str, bool, int)):
        return
    if isinstance(obj, float):
        if not allow_float:
            raise CanonError("floats are not allowed in canonical JSON")
        if not math.isfinite(obj):
            raise CanonError("non-finite float")
        return
    if isinstance(obj, list):
        for v in obj:
            _check(v, allow_float)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise CanonError(f"object key must be a string, got {type(k).__name__}")
            _check(v, allow_float)
        return
    raise CanonError(f"type {type(obj).__name__} is not allowed in canonical JSON")


def _dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def canon(obj: Any) -> bytes:
    """Return the canonical JSON bytes of ``obj``. Raises CanonError on a float."""
    _check(obj, allow_float=False)
    return _dumps(obj).encode("utf-8")


def canon_text(obj: Any) -> str:
    """Canonical JSON as text for rendering tool input inside step text.

    Same rules as ``canon``, except finite floats are allowed and written in
    Python's shortest round-trip form, because real tool inputs carry them.
    """
    _check(obj, allow_float=True)
    return _dumps(obj)
