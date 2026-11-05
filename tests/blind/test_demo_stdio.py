"""The demo's own process preserves Unicode when its terminal uses a legacy encoding."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUOTE = "Synthetic room quote: \u2192 \U0001f600 \u6f22\u5b57"
CODE = f"""
import runpy
import subprocess
import sys
from unittest.mock import patch

def fake_run(argv, **kwargs):
    if 'verify' in argv:
        forged = argv[-1].endswith('q2-forged.json')
        return subprocess.CompletedProcess(
            argv, 2 if forged else 0,
            stdout='PROOF_FAIL synthetic\\n' if forged else 'OK synthetic\\n', stderr='')
    return subprocess.CompletedProcess(argv, 0, stdout={QUOTE!r} + '\\n', stderr='')

sys.argv = ['demo.run', '--log', sys.argv[1]]
with patch('subprocess.run', side_effect=fake_run):
    runpy.run_module('demo.run', run_name='__main__')
"""


def legacy_encoding() -> dict[str, str]:
    """Force a real redirected legacy stream regardless of the host platform."""
    return {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252:strict"}


def test_demo_prints_captured_unicode_as_utf8(tmp_path: Path) -> None:
    """Mock only child CLI output; execute the real demo entrypoint and final print."""
    log = tmp_path / "demo.log"
    result = subprocess.run(
        [sys.executable, "-c", CODE, str(log)],
        cwd=ROOT,
        env=legacy_encoding(),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    output = result.stdout.decode("utf-8")
    assert QUOTE in output
    assert "RESULT PASS: 0 failed commands" in output
    assert output.replace("\r\n", "\n") == log.read_text(encoding="utf-8")


def test_demo_argument_error_is_utf8() -> None:
    """Argument errors preserve the Unicode option name on redirected stderr."""
    option = "--unknown-\u2192-\U0001f600"
    result = subprocess.run(
        [sys.executable, "-m", "demo.run", option],
        cwd=ROOT,
        env=legacy_encoding(),
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert option in result.stderr.decode("utf-8")
