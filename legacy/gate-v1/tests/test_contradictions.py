from ownership_gate.contradictions import Verdict, check_answer
from ownership_gate.transcript import parse_claude_code
from tests.session_builder import SessionBuilder


def session(builder):
    return parse_claude_code(builder.lines())


MIGRATION_FAILED = session(
    SessionBuilder()
    .prompt("add a refunds migration")
    .bash("pytest tests/test_billing.py", ok=True)
    .bash("pytest tests/migrations", ok=False, output="1 failed")
)


def test_claim_against_a_failed_last_run_is_a_contradiction_with_its_step():
    findings = check_answer("I tested the migration.", MIGRATION_FAILED)

    assert len(findings) == 1
    assert findings[0].verdict is Verdict.CONTRADICTED
    assert findings[0].step == 3
    assert "pytest tests/migrations" in findings[0].message


def test_claim_matching_a_passing_run_is_fine():
    assert check_answer("Billing tests pass.", MIGRATION_FAILED) == ()


def test_generic_claim_uses_the_latest_test_run():
    findings = check_answer("All tests pass.", MIGRATION_FAILED)

    assert [f.verdict for f in findings] == [Verdict.CONTRADICTED]


def test_failure_fixed_by_a_later_run_is_fine():
    s = session(
        SessionBuilder().bash("pytest tests/migrations", ok=False).bash("pytest tests/migrations")
    )

    assert check_answer("I reran the migration tests and they pass.", s) == ()


def test_claim_with_no_matching_run_is_unverified_not_contradicted():
    findings = check_answer(
        "I tested the payment webhook by hand and with its tests.", MIGRATION_FAILED
    )

    assert [f.verdict for f in findings] == [Verdict.UNVERIFIED]


def test_explanations_without_a_run_claim_are_not_checked():
    answer = "The auth file changed because refunds need the session user. I will split the PR."

    assert check_answer(answer, MIGRATION_FAILED) == ()


def test_honest_admission_is_not_flagged():
    assert check_answer("I did not run the migration tests yet.", MIGRATION_FAILED) == ()


def test_no_trail_makes_run_claims_unverified():
    findings = check_answer("Tests pass.", None)

    assert [f.verdict for f in findings] == [Verdict.UNVERIFIED]


def test_lint_claim_checks_lint_runs():
    s = session(SessionBuilder().bash("ruff check .", ok=False).bash("pytest"))

    findings = check_answer("Lint is clean, I ran ruff.", s)

    assert [f.verdict for f in findings] == [Verdict.CONTRADICTED]


def test_failure_covered_by_a_broader_later_run_is_not_a_contradiction():
    s = session(
        SessionBuilder().bash("pytest tests/test_parser.py", ok=False).bash("pytest tests/")
    )

    assert check_answer("I fixed the parser test and verified it passes.", s) == ()


def test_suite_wide_claim_with_extra_words_is_still_checked():
    s = session(SessionBuilder().bash("pytest", ok=False))

    findings = check_answer("I reran the full test suite and it passes.", s)

    assert [f.verdict for f in findings] == [Verdict.CONTRADICTED]


def test_negated_clause_does_not_hide_a_claim_in_another_clause():
    findings = check_answer("Tests pass, but I haven't tried Windows.", MIGRATION_FAILED)

    assert [f.verdict for f in findings] == [Verdict.CONTRADICTED]
    assert findings[0].claim == "Tests pass"


def test_words_that_contain_test_are_not_test_claims():
    assert check_answer("I checked the latest typed results.", MIGRATION_FAILED) == ()


def test_an_open_failure_is_cited_even_after_an_unrelated_pass():
    s = session(SessionBuilder().bash("pytest tests/a.py", ok=False).bash("pytest tests/b.py"))

    findings = check_answer("All tests pass.", s)

    assert [f.step for f in findings] == [1]
