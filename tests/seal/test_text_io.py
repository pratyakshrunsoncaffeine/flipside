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


def test_every_text_mode_open_is_utf8_and_lf() -> None:
    """``open()`` and ``Path.open()`` in text mode use the locale encoding on Windows (cp1252),
    so a Switch reply holding a non-cp1252 character crashed the kill-test log, and the rest
    were written as cp1252 bytes in a UTF-8 evidence file."""
    bad = []
    for d in DIRS:
        for f in sorted((ROOT / d).rglob("*.py")):
            if f in SKIP:
                continue
            for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                builtin = isinstance(fn, ast.Name) and fn.id == "open"
                receiver = ast.unparse(fn.value) if isinstance(fn, ast.Attribute) else ""
                method = (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == "open"
                    and receiver not in {"os", "webbrowser"}
                    and not receiver.endswith("opener")  # urllib: opens a request, not a file
                )
                if not (builtin or method):
                    continue
                args = node.args[1:] if builtin else node.args
                modes = [a.value for a in args[:1] if isinstance(a, ast.Constant)]
                modes += [
                    k.value.value
                    for k in node.keywords
                    if k.arg == "mode" and isinstance(k.value, ast.Constant)
                ]
                if any("b" in str(m) for m in modes):
                    continue
                kw = {k.arg or "" for k in node.keywords}
                if not {"encoding", "newline"} <= kw:
                    bad.append(f"{f.relative_to(ROOT)}:{node.lineno}")
    assert not bad, bad


def test_every_os_open_is_binary() -> None:
    """Without ``O_BINARY`` the Windows C runtime writes each LF byte as CR LF, so a random
    32-byte key containing 0x0A was stored longer and then refused (Codex, Windows)."""
    bad = []
    for d in DIRS:
        for f in sorted((ROOT / d).rglob("*.py")):
            if f in SKIP:
                continue
            text = f.read_text(encoding="utf-8")
            for fn in ast.walk(ast.parse(text)):
                if not isinstance(fn, ast.FunctionDef):
                    continue
                opens = [
                    n
                    for n in ast.walk(fn)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "open"
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "os"
                ]
                if opens and "O_BINARY" not in (ast.get_source_segment(text, fn) or ""):
                    bad += [f"{f.relative_to(ROOT)}:{n.lineno}" for n in opens]
    assert not bad, bad
