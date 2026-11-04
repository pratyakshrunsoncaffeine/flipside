import json

import pytest

from ownership_gate.transcript import StepKind, parse_claude_code
from tests.session_builder import SessionBuilder


def test_numbers_prompts_and_tool_calls_in_order():
    lines = (
        SessionBuilder()
        .prompt("Add a refund endpoint to billing")
        .edit("app/billing.py")
        .bash("pytest tests/test_billing.py", ok=False, output="1 failed")
        .lines()
    )

    session = parse_claude_code(lines)

    assert [s.index for s in session.steps] == [1, 2, 3]
    assert [s.kind for s in session.steps] == [StepKind.PROMPT, StepKind.EDIT, StepKind.BASH]
    assert session.steps[0].text == "Add a refund endpoint to billing"
    assert session.steps[1].path == "app/billing.py"
    assert session.steps[2].command == "pytest tests/test_billing.py"
    assert session.steps[2].ok is False
    assert session.steps[2].output == "1 failed"


def test_bash_without_error_flag_is_ok():
    session = parse_claude_code(SessionBuilder().bash("ruff check .").lines())

    assert session.steps[0].ok is True


def test_skips_sidechain_meta_and_system_reminder_records():
    sidechain = {"type": "user", "isSidechain": True, "message": {"content": "subagent prompt"}}
    meta = {"type": "user", "isMeta": True, "message": {"content": "caveat"}}
    reminder = {
        "type": "user",
        "message": {"content": [{"type": "text", "text": "<system-reminder>x</system-reminder>"}]},
    }
    other = {"type": "file-history-snapshot", "snapshot": {}}
    lines = [json.dumps(r) for r in (sidechain, meta, reminder, other)]
    lines += SessionBuilder().prompt("real prompt").lines()

    session = parse_claude_code(lines)

    assert [s.text for s in session.steps] == ["real prompt"]


def test_text_blocks_in_a_prompt_are_joined():
    record = {
        "type": "user",
        "message": {
            "content": [
                {"type": "text", "text": "fix the"},
                {"type": "text", "text": "login bug"},
            ]
        },
    }

    session = parse_claude_code([json.dumps(record)])

    assert session.steps[0].text == "fix the\nlogin bug"


def test_tool_result_content_list_is_flattened():
    tool_use = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "npm test"}},
            ]
        },
    }
    result = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "is_error": True,
                    "content": [{"type": "text", "text": "Exit code 1"}],
                },
            ]
        },
    }

    session = parse_claude_code([json.dumps(tool_use), json.dumps(result)])

    assert session.steps[0].output == "Exit code 1"
    assert session.steps[0].ok is False


def test_bash_with_no_result_has_unknown_outcome():
    tool_use = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest"}},
            ]
        },
    }

    session = parse_claude_code([json.dumps(tool_use)])

    assert session.steps[0].ok is None


@pytest.mark.parametrize(
    "output",
    [
        "The user doesn't want to proceed with this tool use. The tool use was rejected.",
        "Permission for this command was denied by a built-in Claude Code safety check.",
        "[Request interrupted by user for tool use]",
        "<tool_use_error>InputValidationError: command is required</tool_use_error>",
    ],
)
def test_bash_that_never_ran_has_unknown_outcome(output):
    session = parse_claude_code(SessionBuilder().bash("pytest", ok=False, output=output).lines())

    assert session.steps[0].ok is None


def test_bash_failure_output_mentioning_permission_still_fails():
    output = "Exit code 1\nPermission for this file was denied"

    session = parse_claude_code(SessionBuilder().bash("pytest", ok=False, output=output).lines())

    assert session.steps[0].ok is False


def test_failed_or_rejected_edit_is_not_an_edited_path():
    lines = (
        SessionBuilder()
        .edit("a.py")
        .edit("b.py", ok=False, output="The user doesn't want to proceed with this tool use.")
        .edit("c.py", ok=False, output="<tool_use_error>String to replace not found")
        .lines()
    )

    session = parse_claude_code(lines)

    assert session.edited_paths() == {"a.py"}


def test_ignores_malformed_lines():
    lines = ["not json", "", *SessionBuilder().prompt("hello").lines()]

    session = parse_claude_code(lines)

    assert len(session.steps) == 1


def test_write_and_multiedit_record_paths():
    multi = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "m1",
                    "name": "MultiEdit",
                    "input": {"file_path": "a.py", "edits": []},
                },
            ]
        },
    }
    lines = [*SessionBuilder().write("README.md").lines(), json.dumps(multi)]

    session = parse_claude_code(lines)

    assert session.edited_paths() == {"README.md", "a.py"}
