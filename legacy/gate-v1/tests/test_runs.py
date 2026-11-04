from ownership_gate.runs import runs
from ownership_gate.transcript import parse_claude_code
from tests.session_builder import SessionBuilder


def outcomes(builder):
    return [r.ok for r in runs(parse_claude_code(builder.lines()))]


def test_piped_check_reads_its_outcome_from_output():
    b = (
        SessionBuilder()
        .bash("pytest -q | tail -3", ok=True, output="2 failed, 40 passed in 1.2s")
        .bash("pytest -q | tail -3", ok=True, output="42 passed in 1.1s")
        .bash("pytest -q | tail -3", ok=True, output="")
    )

    assert outcomes(b) == [False, True, None]


def test_own_exit_code_is_trusted():
    b = SessionBuilder().bash("pytest", ok=True, output="whatever").bash("pytest", ok=False)

    assert outcomes(b) == [True, False]


def test_failed_chain_blames_the_last_check_unless_output_names_failed_tests():
    lint_failed = SessionBuilder().bash("pytest -q && ruff check .", ok=False, output="E501 x")
    tests_failed = SessionBuilder().bash("pytest -q && ruff check .", ok=False, output="2 failed")

    assert outcomes(lint_failed) == [None, False]
    assert outcomes(tests_failed) == [False, None]


def test_directory_persists_between_commands():
    b = SessionBuilder().bash("cd backend && pytest", ok=False).bash("pytest")

    found = runs(parse_claude_code(b.lines()))

    assert [r.check.workdir for r in found] == ["backend", "backend"]
