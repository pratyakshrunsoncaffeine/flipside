"""flip judge: every check passes on the shipped repo, and a check fails when its claim is false."""

from __future__ import annotations

from pathlib import Path

from flipside import judge


def test_every_check_passes_on_the_shipped_repo() -> None:
    checks = judge.run_all()
    failed = [f"{c.id}: {c.got}" for c in checks if not c.ok]
    assert failed == []
    assert [c.id for c in checks] == [f"J{k}" for k in range(1, 12)]


def test_a_seal_check_fails_when_the_expected_verdict_is_wrong(tmp_path: Path) -> None:
    # The untouched disclosure verifies OK, so a check that expects PROOF_FAIL must fail.
    c = judge.verify_check("JX", "claim", "PROOF_FAIL", None, tmp_path)
    assert not c.ok
    assert c.got.startswith("exit 0, OK leaf 5")


def test_each_tamper_changes_the_disclosure() -> None:
    import json

    base = json.loads((judge.EX / "q2-ok.json").read_text(encoding="utf-8"))
    for tamper in (
        judge._edit_word,
        judge._other_salt,
        judge._other_index,
        judge._short_proof,
        judge._other_commit,
    ):
        d = json.loads(json.dumps(base))
        tamper(d)
        assert d != base, tamper.__name__


def test_summary_line_reads_the_replay_summary() -> None:
    out = 'x\n12:00 --- summary {"card_403": 1, "verdicts": {"OK": 1}}\nRESULT PASS'
    assert judge.summary_line(out) == {"card_403": 1, "verdicts": {"OK": 1}}
    assert judge.summary_line("no summary") == {}


def test_render_ends_with_the_verdict() -> None:
    ok = judge.Check("J1", "claim", "cmd", "exp", "got", True)
    bad = judge.Check("J2", "claim", "cmd", "exp", "got", False)
    assert judge.render([ok], 1.0).endswith("RESULT PASS 1/1 checks in 1.0 s")
    assert judge.render([ok, bad], 1.0).endswith("RESULT FAIL 1/2 checks in 1.0 s")


def test_main_exit_code_without_evidence() -> None:
    assert judge.main(["--no-evidence"]) == 0
