from dataclasses import replace

from ownership_gate.gaps import GapKind, find_gaps
from ownership_gate.model import ChangedFile, CheckRun, PullRequest
from ownership_gate.transcript import parse_claude_code
from tests.session_builder import SessionBuilder

PR = PullRequest(
    repo="acme/shop",
    number=7,
    author="dana",
    title="Add refunds to billing",
    body="Adds a refund endpoint to billing.",
    head_sha="abc1234def",
    files=(ChangedFile("app/billing.py", 40, 2), ChangedFile("tests/test_billing.py", 30, 0)),
    checks=(CheckRun("ci / pytest", "success"),),
)


def session(builder: SessionBuilder):
    return parse_claude_code(builder.lines())


def kinds(report):
    return [g.kind for g in report.gaps]


def test_honest_pr_has_no_gaps():
    s = session(
        SessionBuilder()
        .prompt("Add a refund endpoint to billing with tests")
        .edit("app/billing.py")
        .bash("pytest tests/test_billing.py", ok=False)
        .edit("app/billing.py")
        .bash("pytest", ok=True)
    )

    report = find_gaps(replace(PR, body="Adds refunds. All tests pass."), s)

    assert report.gaps == ()
    assert report.has_trail


def test_failed_check_never_rerun_cites_its_step():
    s = session(
        SessionBuilder()
        .prompt("billing refunds")
        .bash("ls")
        .bash("pytest tests/migrations", ok=False)
    )

    report = find_gaps(PR, s)

    assert kinds(report) == [GapKind.FAILED_NOT_RERUN]
    assert report.gaps[0].step == 3
    assert "Step 3" in report.gaps[0].question


def test_failed_non_check_command_is_not_a_gap():
    s = session(SessionBuilder().prompt("billing").bash("grep -rn refund .", ok=False))

    assert find_gaps(PR, s).gaps == ()


def test_rerun_of_a_narrower_target_leaves_the_failure_open():
    s = session(
        SessionBuilder()
        .prompt("billing")
        .bash("pytest", ok=False)
        .bash("pytest tests/test_billing.py", ok=True)
    )

    assert kinds(find_gaps(PR, s)) == [GapKind.FAILED_NOT_RERUN]


def test_repeated_failures_of_one_check_give_one_gap_at_the_last_step():
    s = session(
        SessionBuilder().prompt("billing").bash("pytest", ok=False).bash("pytest", ok=False)
    )

    report = find_gaps(PR, s)

    assert [g.step for g in report.gaps] == [3]


def test_tests_claimed_but_never_run():
    s = session(SessionBuilder().prompt("billing").edit("app/billing.py"))

    report = find_gaps(replace(PR, body="Refunds. All tests pass."), s)

    assert kinds(report) == [GapKind.TESTS_CLAIMED_NOT_RUN]


def test_named_command_claimed_but_not_run():
    s = session(SessionBuilder().prompt("billing").bash("pytest tests/test_billing.py"))

    report = find_gaps(replace(PR, body="Billing. Ran `npm run lint`."), s)

    assert kinds(report) == [GapKind.COMMAND_CLAIMED_NOT_RUN]
    assert report.gaps[0].subject == "npm run lint"


def test_ci_failing_and_ci_missing():
    s = session(SessionBuilder().prompt("billing").bash("pytest"))

    failing = find_gaps(replace(PR, checks=(CheckRun("ci / pytest", "failure"),)), s)
    missing = find_gaps(replace(PR, body="Billing. Tests pass.", checks=()), s)
    pending = find_gaps(replace(PR, checks=(CheckRun("ci / pytest", None),)), s)

    assert kinds(failing) == [GapKind.CI_FAILING]
    assert kinds(missing) == [GapKind.CI_MISSING]
    assert pending.gaps == ()


def test_file_no_prompt_or_description_mentions():
    s = session(SessionBuilder().prompt("refund endpoint in billing"))
    pr = replace(
        PR,
        files=(*PR.files, ChangedFile("app/auth/session.py", 5, 1), ChangedFile("uv.lock", 900, 0)),
    )

    report = find_gaps(pr, s)

    assert kinds(report) == [GapKind.UNPROMPTED_FILE]
    assert report.gaps[0].subject == "app/auth/session.py"


def test_generic_file_name_is_matched_by_its_folder():
    s = session(SessionBuilder().prompt("fix the checkout page"))
    pr = replace(PR, title="Checkout fix", files=(ChangedFile("web/checkout/index.ts", 3, 1),))

    assert find_gaps(pr, s).gaps == ()


def test_oversize_ignores_lockfiles():
    s = session(SessionBuilder().prompt("billing"))
    big = replace(
        PR, files=(ChangedFile("app/billing.py", 300, 150), ChangedFile("poetry.lock", 5000, 0))
    )
    lock_only = replace(
        PR, files=(ChangedFile("app/billing.py", 10, 0), ChangedFile("poetry.lock", 5000, 0))
    )

    assert kinds(find_gaps(big, s)) == [GapKind.OVERSIZE]
    assert find_gaps(lock_only, s).gaps == ()


def test_no_trail_still_runs_ci_and_size_gaps():
    report = find_gaps(replace(PR, checks=(CheckRun("build", "failure"),)), None)

    assert not report.has_trail
    assert kinds(report) == [GapKind.CI_FAILING]


def test_questions_are_capped_and_ranked():
    b = SessionBuilder().prompt("billing")
    for i in range(4):
        b.bash(f"pytest tests/t{i}.py", ok=False)
    pr = replace(
        PR,
        body="All tests pass.",
        files=(*PR.files, ChangedFile("x/other.py", 1, 0)),
        checks=(CheckRun("ci", "failure"),),
    )

    questions = find_gaps(pr, session(b)).questions()

    assert len(questions) == 5
    assert [q.kind for q in questions] == [GapKind.FAILED_NOT_RERUN] * 4 + [GapKind.CI_FAILING]


def test_file_is_mentioned_by_a_word_of_its_name_or_folder():
    s = session(SessionBuilder().prompt("Add partial refunds with a migration"))
    pr = replace(
        PR,
        title="Refunds",
        files=(
            ChangedFile("db/migrations/0042_refunds.py", 30, 0),
            ChangedFile("web/RefundButton.tsx", 10, 0),
        ),
    )

    assert find_gaps(pr, s).gaps == ()


def test_claimed_test_command_without_ci_is_ci_missing():
    s = session(SessionBuilder().prompt("billing").bash("npm test"))

    report = find_gaps(replace(PR, body="Billing. Ran `npm test`.", checks=()), s)

    assert kinds(report) == [GapKind.CI_MISSING]


def test_piped_failure_is_caught_and_piped_rerun_clears_it():
    failing = session(
        SessionBuilder().prompt("billing").bash("pytest | tail -2", ok=True, output="1 failed")
    )
    fixed = session(
        SessionBuilder()
        .prompt("billing")
        .bash("pytest | tail -2", ok=True, output="1 failed")
        .bash("python -m pytest -q 2>&1 | tail -2", ok=True, output="9 passed")
    )

    assert kinds(find_gaps(PR, failing)) == [GapKind.FAILED_NOT_RERUN]
    assert find_gaps(PR, fixed).gaps == ()


def test_failure_in_a_subdirectory_is_cleared_by_a_rerun_in_the_same_directory():
    s = session(
        SessionBuilder().prompt("billing").bash("cd backend && pytest", ok=False).bash("pytest")
    )

    assert find_gaps(PR, s).gaps == ()
