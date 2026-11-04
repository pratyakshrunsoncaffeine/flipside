"""Coverage from the manifest (docs/seal/SPEC.md, Coverage)."""

from typing import Any

from flipside.seal.coverage import coverage, file_coverage, format_line


def entry(
    i: int,
    step: int,
    files: list[str] | None = None,
    mentions: list[str] | None = None,
    session: int = 0,
    chunk: int = 0,
) -> dict[str, Any]:
    return {
        "i": i,
        "v": 1,
        "session": session,
        "step": step,
        "chunk": chunk,
        "role": "assistant",
        "tools": [],
        "files": files or [],
        "mentions": mentions or [],
        "cmd": None,
        "ok": None,
    }


F = "auth/session.py"
MANIFEST = [
    entry(0, 3, [F]),
    entry(1, 3, [F], chunk=1),
    entry(2, 19, [F]),
    entry(3, 23, mentions=[F]),
    entry(4, 31, mentions=[F]),
    entry(5, 40, ["other.py"]),
    entry(6, 2, [F], session=1),
]


def test_spec_example_line() -> None:
    fc = file_coverage(MANIFEST[:5], [1], F)
    assert format_line(fc) == (
        f"{F}: 4 sealed steps, 1 disclosed, 3 not disclosed (steps 19, 23, 31); 2 by Bash mention"
    )


def test_subagent_steps_are_labelled() -> None:
    fc = file_coverage(MANIFEST, [0, 2, 3, 4], F)
    assert (
        format_line(fc) == f"{F}: 5 sealed steps, 4 disclosed, 1 not disclosed (step s1:2); "
        "2 by Bash mention"
    )


def test_untouched_file_and_json() -> None:
    [fc] = coverage(MANIFEST, [], ["nope.py"])
    assert format_line(fc) == "nope.py: 0 sealed steps, 0 disclosed, 0 not disclosed"
    assert fc.to_json() == {
        "file": "nope.py",
        "sealed": 0,
        "disclosed": 0,
        "not_disclosed": [],
        "by_mention": 0,
    }


def test_file_and_mention_on_same_step_counts_as_file() -> None:
    m = [entry(0, 1, [F], [F])]
    fc = file_coverage(m, [], F)
    assert fc.by_mention == 0 and len(fc.sealed) == 1
    assert format_line(fc) == f"{F}: 1 sealed step, 0 disclosed, 1 not disclosed (step 1)"
