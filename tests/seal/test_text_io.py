"""Every text file the repo writes is UTF-8 with LF line ends on every platform.

On Windows, ``Path.write_text`` without ``newline=""`` writes CRLF and uses the locale
encoding, so regenerated fixtures, examples and session files no longer match their
committed bytes (found by Pratyaksh's Codex on the Windows baseline).
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIRS = ("flipside", "fixtures", "examples", "tests", "killtests")
SKIP = {ROOT / "tests" / "test_board.py"}  # vendored from the board template


def calls(attr: str) -> list[tuple[Path, int, set[str]]]:
    out = []
    for d in DIRS:
        for f in sorted((ROOT / d).rglob("*.py")):
            if f in SKIP:
                continue
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attr
                ):
                    out.append(
                        (f.relative_to(ROOT), node.lineno, {k.arg or "" for k in node.keywords})
                    )
    return out


def test_every_write_text_is_utf8_and_lf() -> None:
    bad = [f"{f}:{n}" for f, n, kw in calls("write_text") if not {"encoding", "newline"} <= kw]
    assert not bad, bad


def test_every_read_text_is_utf8() -> None:
    bad = [f"{f}:{n}" for f, n, kw in calls("read_text") if "encoding" not in kw]
    assert not bad, bad
