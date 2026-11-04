"""Independent synthetic cases with expectations committed before their first run.

The author has seen the existing rules; this is not a claim of unseen-rule evaluation.
Exercise the public CLI, both agents, real git seals and proofs, and FakeSwitch.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.seal.builder import SessionBuilder, tool

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures" / "b"
SCENARIOS: dict[str, Any] = json.loads((FIXTURES / "scenarios.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_independent_case_via_public_cli(name: str, tmp_path: Path) -> None:
    """Each manually specified outcome must hold for a complete sealed review round."""
    raw = dict(SCENARIOS[name])
    steps = raw.pop("session_steps")
    case = tmp_path / "case"
    case.mkdir()
    (case / "case.json").write_text(json.dumps(raw), encoding="utf-8", newline="")
    expected = (FIXTURES / name / "expected.json").read_bytes()
    (case / "expected.json").write_bytes(expected)
    session = SessionBuilder(".")
    session.user("Synthetic independent test case. Review the changes recorded below.")
    for index, step in enumerate(steps):
        tid = f"b-{index}"
        if "edit" in step:
            session.assistant(
                tool(
                    tid,
                    "Edit",
                    file_path=step["edit"],
                    old_string=step["old"],
                    new_string=step["new"],
                )
            )
            session.result(tid, "Edit applied.")
        else:
            session.assistant(tool(tid, "Bash", command=step["command"]))
            session.result(tid, step["output"], is_error=step["error"])
    session.write(case / "session.jsonl")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "flipside.cli",
            "replay",
            "--offline",
            "--no-evidence",
            "--case",
            str(case),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    transcript = result.stdout + result.stderr
    (tmp_path / "transcript.log").write_text(transcript, encoding="utf-8", newline="")
    assert result.returncode == 0, transcript
    assert "RESULT PASS" in result.stdout, transcript
