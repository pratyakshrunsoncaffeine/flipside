import pytest

from ownership_gate.gaps import find_gaps
from ownership_gate.gate import Gate, NotAuthorError, Status
from ownership_gate.model import ChangedFile, CheckRun, PullRequest
from ownership_gate.transcript import parse_claude_code
from tests.session_builder import SessionBuilder

SESSION = parse_claude_code(
    SessionBuilder()
    .prompt("add a refunds migration to billing")
    .bash("pytest tests/migrations", ok=False)
    .lines()
)
PR = PullRequest(
    repo="acme/shop",
    number=7,
    author="dana",
    title="Refunds",
    body="Billing refunds. All tests pass.",
    head_sha="abc1234",
    files=(ChangedFile("app/billing.py", 10, 0), ChangedFile("app/auth.py", 2, 0)),
    checks=(CheckRun("ci", "success"),),
)


def open_gate() -> Gate:
    return Gate.open(find_gaps(PR, SESSION), SESSION)


def test_opens_with_one_question_per_gap():
    gate = open_gate()

    assert len(gate.questions) == 2
    assert gate.status is Status.AWAITING_ANSWERS


def test_only_the_author_can_answer():
    with pytest.raises(NotAuthorError):
        open_gate().answer("rev-bot", "1: fine")


def test_contradicted_answer_blocks_then_revision_clears():
    gate, _ = open_gate().answer(
        "dana", "Q1: I tested the migration.\nQ2: auth needs the session user."
    )

    assert gate.status is Status.CONTRADICTED
    assert gate.latest(1).findings[0].step == 2

    gate, new = gate.answer(
        "Dana", "1: You're right, the migration test fails. Fixed in a follow-up push."
    )

    assert [r.question for r in new] == [1]
    assert gate.status is Status.CLEARED
    assert len(gate.history(1)) == 2


def test_unnumbered_chat_is_not_an_answer():
    _, new = open_gate().answer("dana", "brb, checking the migration")

    assert new == ()


def test_numbers_inside_an_answer_stay_text():
    gate, new = open_gate().answer("dana", "1: Two steps:\n2) rerun it\n3.5 seconds")

    assert [r.question for r in new] == [1]
    assert "2) rerun it" in gate.latest(1).text


def test_markers_must_increase_and_open_the_message():
    _, new = open_gate().answer("dana", "2: auth needs the user.\n1: retested")

    assert [r.question for r in new] == [2]


def test_out_of_range_numbers_are_ignored():
    _, new = open_gate().answer("dana", "9: nothing")

    assert new == ()


def test_pr_without_gaps_is_cleared_at_once():
    honest = PullRequest(
        repo="a/b",
        number=1,
        author="dana",
        title="Billing refunds",
        body="Billing.",
        head_sha="1",
        files=(ChangedFile("app/billing.py", 3, 0),),
    )

    clean = parse_claude_code(SessionBuilder().prompt("billing refunds").bash("pytest").lines())

    gate = Gate.open(find_gaps(honest, clean), clean)

    assert gate.questions == ()
    assert gate.status is Status.CLEARED
