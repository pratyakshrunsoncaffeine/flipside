"""``flip`` writes UTF-8 to a pipe on every OS.

On Windows, Python encodes a redirected stdout or stderr with the locale code page
(cp1252), so any character outside it (an arrow in a session quote, an emoji in a room
message, a path) raised UnicodeEncodeError and ended the run.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "missing-→-\U0001f600.json"


def python(*args: str, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONUTF8", "PYTHONIOENCODING"}}
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        env={**env, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        check=False,
    )


def test_flip_writes_utf8_to_a_piped_stderr(tmp_path: Path) -> None:
    p = python(
        "-m", "flipside.cli", "verify", "--commit", "x", "--manifest", "m", NAME, cwd=tmp_path
    )
    err = p.stderr.decode("utf-8")
    assert p.returncode == 1
    assert NAME in err, err


def test_utf8_stdio_lets_a_piped_stdout_take_any_character(tmp_path: Path) -> None:
    code = f"from flipside.cli import utf8_stdio; utf8_stdio(); print({NAME!r})"
    p = python("-c", code, cwd=tmp_path)
    assert p.returncode == 0, p.stderr.decode("utf-8", "replace")
    assert p.stdout.decode("utf-8").strip() == NAME
