"""Finds what a PR description claims was verified.

Two kinds of claim: a plain-language "tests pass", and a command in a code span
(`pytest tests/x.py`) in a sentence that says it ran or passed. Unchecked template
boxes, negated sentences and instructions to reviewers ("run `pytest`") are not claims,
because a false flag on an honest PR costs more than a missed one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ownership_gate.commands import Check, classify

TESTS_PASS = re.compile(
    r"\b(?:all\s+)?(?:unit\s+|integration\s+|e2e\s+)?tests?\s+(?:are\s+|now\s+|all\s+)?"
    r"(?:pass(?:es|ed|ing)?|green)\b"
    r"|\btest\s+suite\s+(?:passes|passed|is\s+green)\b"
    r"|\b(?:i\s+)?(?:ran|run)\s+(?:the\s+|all\s+)?(?:unit\s+|integration\s+)?tests\b"
    r"|\btested\s+(?:locally|it|this|end\s+to\s+end)\b"
    r"|^\s*[-*]\s*\[x\]\s*(?:unit\s+)?tests?\b",
    re.IGNORECASE | re.MULTILINE,
)
UNCHECKED_BOX = re.compile(r"^\s*[-*]\s*\[\s\]")
NEGATION = re.compile(
    r"\b(?:not|never|no|without|cannot|unable)\b|\w+n't\b|\bcan't\b|\bwon't\b", re.IGNORECASE
)
RAN_CONTEXT = re.compile(
    r"\b(?:ran|executed|verified|checked|pass(?:es|ed|ing)?|green|clean|succeeds?|succeeded)\b",
    re.IGNORECASE,
)
CODE_SPAN = re.compile(r"`([^`\n]+)`")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Claims:
    tests_pass: bool
    commands: tuple[tuple[str, Check], ...]


def parse_claims(body: str) -> Claims:
    sentences = [s for line in body.splitlines() for s in _sentences(line)]
    return Claims(
        tests_pass=any(TESTS_PASS.search(s) for s in sentences),
        commands=_claimed_commands(sentences),
    )


def _sentences(line: str) -> list[str]:
    """Claim-bearing sentences of one line: unchecked boxes and negated sentences drop out."""
    if UNCHECKED_BOX.match(line):
        return []
    return [
        s
        for s in SENTENCE_END.split(line)
        if s.strip() and not s.rstrip().endswith("?") and not NEGATION.search(s)
    ]


def _claimed_commands(sentences: list[str]) -> tuple[tuple[str, Check], ...]:
    found: dict[str, Check] = {}
    for sentence in sentences:
        if not RAN_CONTEXT.search(CODE_SPAN.sub("", sentence)):
            continue
        for text in CODE_SPAN.findall(sentence):
            command = text.strip()
            check = classify(command)
            if check is not None and command not in found:
                found[command] = check
    return tuple(found.items())
