import pytest

from ownership_gate.claims import parse_claims


@pytest.mark.parametrize(
    "body",
    [
        "Adds refunds. All tests pass.",
        "tests are green",
        "I ran the tests locally",
        "Tested locally against staging.",
        "## Checklist\n- [x] Tests",
        "The test suite passes.",
    ],
)
def test_detects_tests_pass_claims(body):
    assert parse_claims(body).tests_pass


@pytest.mark.parametrize(
    "body",
    [
        "Adds refunds.",
        "I have not run the tests yet.",
        "Tests not passing on Windows, help wanted",
        "- [ ] Tests",
        "- [ ] Tests pass",
        "Adds a test for refunds.",
        "Couldn't run the tests, CI is down.",
        "Tests pass? I can't tell yet.",
        "Tested manually in the browser.",
    ],
)
def test_ignores_bodies_without_a_tests_pass_claim(body):
    assert not parse_claims(body).tests_pass


def test_negation_in_one_sentence_does_not_hide_a_claim_in_another():
    assert parse_claims("No schema change. All tests pass.").tests_pass


def test_extracts_commands_said_to_have_run():
    body = "Ran `pytest tests/test_billing.py` and `ls`. `npm run lint` is clean."

    commands = [c for c, _ in parse_claims(body).commands]

    assert commands == ["pytest tests/test_billing.py", "npm run lint"]


@pytest.mark.parametrize(
    "body",
    [
        "Added a `make test` target.",
        "Reviewers: run `pytest` before merging.",
        "To try it:\n```\n$ npm run lint\n```",
        "I did not run `pytest` yet.",
    ],
)
def test_commands_not_said_to_have_run_are_not_claims(body):
    assert parse_claims(body).commands == ()
