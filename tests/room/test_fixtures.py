"""M2 and M5: every fixture case gives its expected outcome offline; fixtures regenerate."""

import subprocess
import sys
from pathlib import Path

import pytest

from flipside.room.replay import run_offline
from flipside.room.run import compare
from flipside.room.scenario import load_case, materialize

ROOT = Path(__file__).resolve().parents[2]
CASES = sorted((ROOT / "fixtures" / "cases").iterdir())


@pytest.mark.parametrize("case_dir", CASES, ids=[c.name for c in CASES])
def test_case_outcome(case_dir: Path, tmp_path: Path) -> None:
    case = load_case(case_dir)
    world = materialize(case, tmp_path / "world")
    lines: list[str] = []
    result = run_offline(world, lines.append, tmp_path)
    assert result.brief is not None, "\n".join(lines)
    assert compare(result.summary(), case.expected) == [], "\n".join(lines)


def test_eight_cases_four_hidden_two_honest_two_adversarial() -> None:
    names = [c.name for c in CASES]
    assert len(names) == 8
    assert sum(n.startswith("honest-") for n in names) == 2


def test_honest_cases_have_zero_gaps_and_a_clean_brief(tmp_path: Path) -> None:
    for c in CASES:
        if not c.name.startswith("honest-"):
            continue
        world = materialize(load_case(c), tmp_path / c.name)
        result = run_offline(world, lambda _m: None, tmp_path)
        assert result.brief is not None
        assert result.brief["gaps"] == [] and result.brief["contradictions"] == []
        assert result.brief["refused"] == []


def test_fixtures_regenerate_byte_for_byte(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "fixtures" / "build_fixtures.py"), str(tmp_path)],
        check=True,
        capture_output=True,
    )
    for d in CASES:
        for f in sorted(p for p in d.rglob("*") if p.is_file()):
            rel = f.relative_to(d)
            assert (tmp_path / d.name / rel).read_bytes() == f.read_bytes(), f"{d.name}/{rel}"
