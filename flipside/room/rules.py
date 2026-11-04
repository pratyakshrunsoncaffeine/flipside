"""Deterministic reviewer-side rules (docs/BUILD.md section 7): gaps, leaf selection,
contradictions. Inputs are public: PR text, changed files, check runs, the manifest."""

import posixpath
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

MAX_QUESTIONS = 5
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
_TESTS_PASS = re.compile(r"\btests? (pass|passed|passing|green)\b", re.I)
_ANSWER_PASS = re.compile(r"\b(pass|passed|green)\b", re.I)
_FAIL_TEXT = re.compile(r"FAILED|Error:|(?i:exit code [1-9])")

StepId = tuple[int, int]


@dataclass(frozen=True)
class CheckRun:
    name: str
    conclusion: str | None


@dataclass(frozen=True)
class PRData:
    """Everything public the reviewer side reads about one PR."""

    number: int
    title: str
    body: str
    author: str
    files: tuple[str, ...]
    checks: tuple[CheckRun, ...] = ()


@dataclass(frozen=True)
class Gap:
    kind: str
    text: str
    file: str | None = None
    check: str | None = None
    step: StepId | None = None


@dataclass(frozen=True)
class Selection:
    """Leaves requested for one gap. ``anchored`` leaves must touch the gap's file."""

    leaves: tuple[int, ...] = ()
    anchored: frozenset[int] = field(default_factory=frozenset)


def steps_of(manifest: Sequence[dict[str, Any]]) -> dict[StepId, list[dict[str, Any]]]:
    """Manifest entries grouped by (session, step), in manifest order."""
    out: dict[StepId, list[dict[str, Any]]] = {}
    for e in manifest:
        out.setdefault((e["session"], e["step"]), []).append(e)
    return out


def _touches(entries: list[dict[str, Any]], f: str) -> bool:
    return f in entries[0]["files"] or f in entries[0]["mentions"]


_ADDS_TESTS = re.compile(
    r"\b(with|adds?|added|adding|new|updated?|more)\s+(unit\s+|integration\s+)?tests?\b"
    r"|\btests?\s+for\b",
    re.I,
)
_TEST_NAME = re.compile(r"^(test_(?P<a>.+)|(?P<b>.+?)(_test|\.test|\.spec))$")


def tested_subject(f: str) -> str | None:
    """``report`` for ``tests/test_report.py``, ``report_test.go`` or ``report.spec.ts``;
    None for a file that is not a test."""
    name = posixpath.basename(f).lower()
    stem = (
        name.split(".")[0] if ".test." in name or ".spec." in name else posixpath.splitext(name)[0]
    )
    if ".test." in name or ".spec." in name:
        return stem or None
    hit = _TEST_NAME.match(stem)
    return (hit.group("a") or hit.group("b")) if hit else None


def _mentioned(f: str, pr: PRData) -> bool:
    """F is named by path or by basename without extension. A test file also counts when
    the description says it adds or changes tests and names the test's subject."""
    text = f"{pr.title}\n{pr.body}".lower()
    stem = posixpath.splitext(posixpath.basename(f))[0].lower()
    if f.lower() in text or (bool(stem) and stem in text):
        return True
    subject = tested_subject(f)
    return subject is not None and bool(_ADDS_TESTS.search(text)) and subject in text


def never_ran(entry: dict[str, Any]) -> bool:
    """A Bash result whose call never ran (C14): rejected, interrupted or denied."""
    return (
        entry.get("role") == "tool_result"
        and "Bash" in entry.get("tools", [])
        and entry["ok"] is None
    )


def _last_test_result(steps: dict[StepId, list[dict[str, Any]]]) -> StepId | None:
    """The latest sealed test result that actually ran."""
    found = [
        k
        for k, es in steps.items()
        if es[0]["role"] == "tool_result" and es[0]["cmd"] == "test" and not never_ran(es[0])
    ]
    return max(found) if found else None


def gaps(pr: PRData, manifest: Sequence[dict[str, Any]] | None) -> list[Gap]:
    """All gaps, in rule order CI, TESTS, SCOPE, UNSEALED. A PR with no seal gets
    ``manifest=None``: CI and TESTS-by-text still apply, file rules use no evidence."""
    steps = steps_of(manifest or [])
    out = [
        Gap("CI", f"Check `{c.name}` failed on the sealed commit. What happened?", check=c.name)
        for c in pr.checks
        if c.conclusion == "failure"
    ]
    if _TESTS_PASS.search(pr.body):
        last = _last_test_result(steps)
        if last is None:
            out.append(
                Gap(
                    "TESTS", "The PR says tests pass. No sealed step ran tests. Which run is right?"
                )
            )
        elif steps[last][0]["ok"] is False:
            out.append(
                Gap(
                    "TESTS",
                    "The PR says tests pass. The last sealed test run did "
                    f"not pass (step `{last[1]}`). Which run is right?",
                    step=last,
                )
            )
    for f in pr.files:
        if not _mentioned(f, pr) and any(_touches(es, f) for es in steps.values()):
            out.append(
                Gap(
                    "SCOPE",
                    f"`{f}` changed and the PR description does not mention it. Why?",
                    file=f,
                )
            )
    for f in pr.files:
        if not any(_touches(es, f) for es in steps.values()):
            out.append(
                Gap(
                    "UNSEALED",
                    f"No sealed step touched `{f}`. Was it changed outside the agent?",
                    file=f,
                )
            )
    return out


def asked(all_gaps: Sequence[Gap]) -> tuple[list[Gap], list[Gap]]:
    """The first five gaps are asked; the rest are listed in the brief as not asked."""
    return list(all_gaps[:MAX_QUESTIONS]), list(all_gaps[MAX_QUESTIONS:])


def _leaves(steps: dict[StepId, list[dict[str, Any]]], ids: Sequence[StepId]) -> list[int]:
    return [e["i"] for k in ids for e in steps[k]]


def _cap(leaves: Sequence[int]) -> tuple[int, ...]:
    """At most 8 leaves, most recent first."""
    return tuple(sorted(set(leaves), reverse=True)[:8])


def select(gap: Gap, manifest: Sequence[dict[str, Any]]) -> Selection:
    """Leaves requested for a gap (docs/BUILD.md 7.3)."""
    steps = steps_of(manifest)
    order = sorted(steps)
    if gap.kind in ("CI", "TESTS"):
        result = _last_test_result(steps)
        if result is None:
            return Selection()
        calls = [
            k
            for k in order
            if k < result
            and k[0] == result[0]
            and steps[k][0]["role"] == "assistant"
            and steps[k][0]["cmd"] == "test"
        ]
        ids = [*calls[-1:], result]
        return Selection(_cap(_leaves(steps, ids)))
    if gap.kind == "SCOPE" and gap.file:
        f = gap.file
        edits = [
            k
            for k in order
            if steps[k][0]["role"] == "assistant"
            and f in steps[k][0]["files"]
            and EDIT_TOOLS & set(steps[k][0]["tools"])
        ]
        if not edits:
            edits = [
                k
                for k in order
                if steps[k][0]["role"] == "assistant" and f in steps[k][0]["mentions"]
            ]
        if not edits:
            return Selection()
        edit = edits[-1]
        context: list[StepId] = []
        for k in reversed([k for k in order if k < edit and k[0] == edit[0]]):
            role = steps[k][0]["role"]
            if role == "user":
                break
            if role == "assistant" and not steps[k][0]["tools"]:
                context = [k]
                break
        anchored = _leaves(steps, [edit])
        chosen = _cap([*anchored, *_leaves(steps, context)])
        return Selection(chosen, frozenset(anchored) & frozenset(chosen))
    return Selection()


@dataclass(frozen=True)
class Contradiction:
    rule: str
    q: int
    i: int
    detail: str


def contradictions(
    q: int,
    answer: str | None,
    gap: Gap,
    verified: Sequence[dict[str, Any]],
    anchored: frozenset[int],
) -> list[Contradiction]:
    """Rules on verified bytes only (docs/BUILD.md 7.4). ``verified`` holds dicts with
    ``i`` and ``leaf`` for leaves that verified OK for question q."""
    out: list[Contradiction] = []
    for v in verified:
        leaf, i = v["leaf"], v["i"]
        if (
            answer
            and _ANSWER_PASS.search(answer)
            and not never_ran(leaf)
            and (leaf["ok"] is False or _FAIL_TEXT.search(leaf["text"]))
        ):
            out.append(
                Contradiction(
                    "C-TESTS", q, i, "the answer says tests pass; the verified leaf shows a failure"
                )
            )
        if (
            gap.file
            and i in anchored
            and gap.file not in leaf["files"]
            and gap.file not in leaf["mentions"]
        ):
            out.append(Contradiction("C-FILE", q, i, f"leaf does not touch {gap.file}"))
    return out
