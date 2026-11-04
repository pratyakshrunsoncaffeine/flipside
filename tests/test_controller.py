from ownership_gate import render
from ownership_gate.controller import GateController
from ownership_gate.gate import Status
from ownership_gate.model import ChangedFile, CheckRun, PullRequest
from ownership_gate.transcript import parse_claude_code
from tests.session_builder import SessionBuilder

SESSION = parse_claude_code(
    SessionBuilder()
    .prompt("billing refunds migration")
    .bash("pytest tests/migrations", ok=False)
    .lines()
)
PR = PullRequest(
    repo="acme/shop",
    number=7,
    author="dana",
    title="Billing refunds",
    body="All tests pass.",
    head_sha="abc1234",
    files=(ChangedFile("app/billing.py", 10, 0),),
    checks=(CheckRun("ci", "success"),),
)


def test_full_flow_pages_the_reviewer_once_after_clearing():
    ctl = GateController(reviewer="sam")

    opening = ctl.open(PR, SESSION)
    blocked = ctl.on_message(PR.key, "dana", "1: I tested the migration.")
    cleared = ctl.on_message(
        PR.key, "dana", "1: It failed and I did not rerun it; fix pushed next."
    )
    status_when_cleared = ctl.status(PR.key)
    after = ctl.on_message(PR.key, "dana", "1: I tested the migration.")

    assert "Step 2" in opening[0]
    assert "Contradiction in answer 1" in blocked[0]
    assert status_when_cleared is Status.CLEARED
    assert len(cleared) == 2
    assert cleared[1].startswith("@sam **acme/shop#7 is ready for review.**")
    assert "Revised 1 time(s)" in cleared[1]
    assert "Contradiction in answer 1" in after[0]
    assert after[1].startswith("@sam, the author revised answer 1 after you were paged and")
    assert len(after) == 2, "the reviewer is not paged twice"


def test_unnumbered_message_gets_a_hint():
    ctl = GateController()
    ctl.open(PR, SESSION)

    assert ctl.on_message(PR.key, "dana", "brb") == [render.ANSWER_HINT]


def test_non_author_is_refused_and_gate_unchanged():
    ctl = GateController()
    ctl.open(PR, SESSION)

    reply = ctl.on_message(PR.key, "reviewer-agent", "1: tested")

    assert reply == ["Only dana can answer for this PR."]
    assert ctl.status(PR.key) is Status.AWAITING_ANSWERS


def test_pr_without_gaps_pages_at_once_and_no_trail_is_flagged():
    clean = PullRequest(
        repo="a/b", number=1, author="dana", title="Docs", body="Docs.", head_sha="1"
    )

    messages = GateController(reviewer="sam").open(clean, None)

    assert "**No trail.**" in messages[0]
    assert "ready for review" in messages[1]


def test_new_head_commit_needs_a_new_gate():
    ctl = GateController()
    ctl.open(PR, SESSION)

    assert ctl.is_current(PR)
    assert not ctl.is_current(PullRequest(**{**PR.__dict__, "head_sha": "fff0000"}))
