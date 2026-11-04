"""G8: the committed examples verify offline, and examples/build.py regenerates them exactly."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "examples"


def flip_verify(disclosure: str) -> subprocess.CompletedProcess[str]:
    commit = (EX / "commit.txt").read_text(encoding="utf-8").strip()
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "flipside.cli",
            "verify",
            "--bundle",
            str(EX / "seal.bundle"),
            "--commit",
            commit,
            "--manifest",
            str(EX / "manifest.json"),
            str(EX / disclosure),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_g8_ok_and_forged() -> None:
    ok = flip_verify("q2-ok.json")
    assert ok.returncode == 0 and ok.stdout.startswith("OK leaf "), ok.stdout + ok.stderr
    forged = flip_verify("q2-forged.json")
    assert forged.returncode == 2 and forged.stdout.startswith("PROOF_FAIL"), forged.stdout


def test_examples_regenerate_byte_for_byte(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(EX / "build.py"), str(tmp_path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        check=True,
        capture_output=True,
    )
    for name in ("session.jsonl", "manifest.json", "q2-ok.json", "q2-forged.json", "commit.txt"):
        assert (tmp_path / name).read_bytes() == (EX / name).read_bytes(), name
