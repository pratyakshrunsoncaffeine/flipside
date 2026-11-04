"""Plays every fixture scenario through the CLI, as a judge would, and checks the outcome."""

import json
from pathlib import Path

import pytest

from ownership_gate.cli import main
from ownership_gate.events import read_events

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
EXPECTED = {
    "migration-claim": {"check_exit": 1, "paged": True, "contradictions": 1, "refusals": 1},
    "honest": {"check_exit": 0, "paged": True, "contradictions": 0, "refusals": 0},
    "claimed-command": {"check_exit": 1, "paged": False, "contradictions": 0, "refusals": 0},
    "no-trail": {"check_exit": 1, "paged": True, "contradictions": 0, "refusals": 0},
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_scenario_outcome(name, tmp_path, capsys):
    folder = FIXTURES / name
    record = tmp_path / "events.jsonl"
    transcript = folder / "full.jsonl"
    check_args = ["check", "--pr-json", str(folder / "pr.json")]
    if transcript.exists():
        check_args += ["--transcript", str(transcript)]

    check_exit = main(check_args)
    main(["demo", str(folder), "--record", str(record)])
    events = read_events(record)
    gate_text = [e.text for e in events if e.kind == "agent"]

    expected = EXPECTED[name]
    assert check_exit == expected["check_exit"]
    assert any("is ready for review" in t for t in gate_text) == expected["paged"]
    assert sum(t.count("**Contradiction") for t in gate_text) == expected["contradictions"]
    assert sum(t.startswith("Only ") for t in gate_text) == expected["refusals"]


def test_replay_prints_a_recorded_log(tmp_path, capsys):
    record = tmp_path / "events.jsonl"
    main(["demo", str(FIXTURES / "migration-claim"), "--record", str(record)])
    capsys.readouterr()

    main(["replay", str(record)])

    printed = capsys.readouterr().out
    assert "[human] dana" in printed
    assert "Step 6 shows `pytest tests/migrations` failed" in printed


def test_every_fixture_has_a_pr_and_answers():
    for folder in FIXTURES.iterdir():
        assert json.loads((folder / "pr.json").read_text())["author"] == "dana"
        assert isinstance(json.loads((folder / "answers.json").read_text()), list)
