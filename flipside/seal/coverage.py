"""Per-file coverage from the manifest (docs/seal/SPEC.md, Coverage).

Computed by the reviewer's side from public data: the manifest and the set
of leaf indexes that verified OK.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

StepId = tuple[int, int]


@dataclass(frozen=True)
class FileCoverage:
    """Coverage of one file. Steps are (session, step) pairs, in order."""

    file: str
    sealed: list[StepId]
    disclosed: list[StepId]
    withheld: list[StepId]
    by_mention: int

    def to_json(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "sealed": len(self.sealed),
            "disclosed": len(self.disclosed),
            "withheld": [list(s) for s in self.withheld],
            "by_mention": self.by_mention,
        }


def step_label(s: StepId) -> str:
    """Session 0 steps print as their number; subagent steps as ``s<session>:<step>``."""
    return str(s[1]) if s[0] == 0 else f"s{s[0]}:{s[1]}"


def file_coverage(
    manifest: Sequence[dict[str, Any]], verified: Iterable[int], file: str
) -> FileCoverage:
    """Touching steps have ``file`` in files or mentions; a step is disclosed when any of
    its leaves verified OK. ``by_mention`` counts steps that touch it only by Bash mention."""
    ok = set(verified)
    touching: dict[StepId, bool] = {}
    disclosed: set[StepId] = set()
    for e in manifest:
        sid = (e["session"], e["step"])
        if file in e["files"]:
            touching[sid] = False
        elif file in e["mentions"]:
            touching.setdefault(sid, True)
        if e["i"] in ok:
            disclosed.add(sid)
    sealed = sorted(touching)
    return FileCoverage(
        file,
        sealed,
        [s for s in sealed if s in disclosed],
        [s for s in sealed if s not in disclosed],
        sum(1 for s in sealed if touching[s]),
    )


def coverage(
    manifest: Sequence[dict[str, Any]], verified: Iterable[int], files: Sequence[str]
) -> list[FileCoverage]:
    """Coverage for each file, in the order given."""
    ok = list(verified)
    return [file_coverage(manifest, ok, f) for f in files]


def format_line(fc: FileCoverage) -> str:
    """``auth/session.py: 4 sealed steps, 1 disclosed, 3 withheld (steps 19, 23, 31); 2 by
    Bash mention``."""
    word = "step" if len(fc.sealed) == 1 else "steps"
    line = (
        f"{fc.file}: {len(fc.sealed)} sealed {word}, {len(fc.disclosed)} disclosed, "
        f"{len(fc.withheld)} withheld"
    )
    if fc.withheld:
        line += (
            f" ({'step' if len(fc.withheld) == 1 else 'steps'} "
            f"{', '.join(step_label(s) for s in fc.withheld)})"
        )
    if fc.by_mention:
        line += f"; {fc.by_mention} by Bash mention"
    return line
