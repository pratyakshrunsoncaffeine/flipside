"""Secret scan for leaves before they reach an approval card (docs/BUILD.md section 8).

Hits report the kind and the character span only, never the matched bytes.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b")),
    (
        "aws_secret_key",
        re.compile(r"(?i)aws_?secret_?access_?key[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{40}"),
    ),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b")),
    ("github_pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,255}\b")),
    (
        "private_key",
        re.compile(
            r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"
            r"(?:.*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|.*\Z)",
            re.S,
        ),
    ),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")),
    ("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("api_key", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}")),
)
_ENV_LINE = re.compile(
    r"(?m)(?:^|(?<=[\s;&|(]))(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*[\"']?([^\s\"'#;&|]{16,})"
)
ENTROPY_MIN = 3.5


@dataclass(frozen=True)
class Hit:
    """A secret-like span in a text. ``start`` and ``end`` are character offsets."""

    kind: str
    start: int
    end: int


def entropy(s: str) -> float:
    """Shannon entropy in bits per character."""
    if not s:
        return 0.0
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


def scan(text: str) -> list[Hit]:
    """Every secret-like span in ``text``, sorted by position."""
    hits = [Hit(kind, m.start(), m.end()) for kind, rx in PATTERNS for m in rx.finditer(text)]
    for m in _ENV_LINE.finditer(text):
        if entropy(m.group(2)) >= ENTROPY_MIN:
            hits.append(Hit("env_value", m.start(2), m.end(2)))
    return sorted(hits, key=lambda h: (h.start, h.end, h.kind))


def overlapping(hits: list[Hit], start: int, end: int) -> list[Hit]:
    """Hits that overlap the half-open span [start, end)."""
    return [h for h in hits if h.start < end and h.end > start]
