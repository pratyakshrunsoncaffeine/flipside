"""Session JSONL to steps, metadata and chunks (docs/seal/SPEC.md, Steps to Chunks)."""

import base64
import hashlib
from pathlib import Path

import pytest

from flipside.seal.steps import (
    SessionError,
    Step,
    chunks,
    classify_cmd,
    parse_session,
    sealed_prefix,
)
from tests.seal.builder import SessionBuilder, text, thinking, tool

REPO = "/work/repo"
CHANGED = ["auth/session.py", "reports/export.py"]


def parse(b: SessionBuilder, **kw: object) -> list[Step]:
    data = b.text().encode()
    return parse_session(data, 0, repo_root=REPO, changed_files=CHANGED, **kw)  # type: ignore[arg-type]


# --- chunks -----------------------------------------------------------------


def test_empty_text_gives_one_empty_chunk() -> None:
    assert chunks("") == [""]


def test_short_text_one_chunk() -> None:
    assert chunks("hello world") == ["hello world"]


def test_exactly_300_is_one_chunk() -> None:
    assert chunks("a" * 300) == ["a" * 300]


def test_no_whitespace_cuts_at_300() -> None:
    assert [len(c) for c in chunks("a" * 650)] == [300, 300, 50]


def test_cut_after_last_space_inside_window() -> None:
    out = chunks("word " * 130)
    assert all(len(c) <= 300 for c in out)
    assert "".join(out) == "word " * 130
    assert all(c.endswith(" ") for c in out[:-1])


def test_space_at_index_300_is_outside_window() -> None:
    """v1 example.py cut after a space at index 300 and produced a 301-char chunk."""
    t = "a" * 299 + "b" + " " + "c" * 10
    out = chunks(t)
    assert [len(c) for c in out] == [300, 11]


def test_newline_counts_as_cut_point() -> None:
    t = "x" * 200 + "\n" + "y" * 200
    assert chunks(t) == ["x" * 200 + "\n", "y" * 200]


def test_crlf_and_nfc() -> None:
    assert chunks("a\r\nb") == ["a\nb"]
    assert chunks("é") == ["é"]


def test_code_points_not_bytes() -> None:
    assert [len(c) for c in chunks("é" * 301)] == [300, 1]


def test_chunks_reassemble() -> None:
    t = ("lorem ipsum dolor " * 40 + "z" * 400 + "\n") * 3
    assert "".join(chunks(t)) == t


# --- sealed prefix ------------------------------------------------------------


def test_sealed_prefix_cuts_at_last_complete_line() -> None:
    assert sealed_prefix(b'{"a":1}\n{"b":') == b'{"a":1}\n'
    assert sealed_prefix(b"no newline") == b""
    assert sealed_prefix(b"x\n") == b"x\n"


# --- steps --------------------------------------------------------------------


def test_user_string_assistant_merge_and_tool_result() -> None:
    b = SessionBuilder(REPO)
    b.user("Add CSV export.")
    b.assistant(
        thinking("private"),
        text("Editing."),
        tool("t1", "Edit", file_path=f"{REPO}/reports/export.py", old_string="a", new_string="b"),
    )
    b.result("t1", "ok")
    steps = parse(b)
    assert [s.role for s in steps] == ["user", "assistant", "tool_result"]
    assert [s.step for s in steps] == [0, 1, 2]
    a = steps[1]
    assert (
        a.text == 'Editing.\n[tool Edit] {"file_path":"/work/repo/reports/export.py",'
        '"new_string":"b","old_string":"a"}'
    )
    assert "private" not in a.text
    assert a.tools == ["Edit"] and a.files == ["reports/export.py"]
    assert a.cmd is None and a.ok is None and a.mentions == []
    r = steps[2]
    assert r.tools == ["Edit"] and r.files == ["reports/export.py"] and r.text == "ok"
    assert r.ok is None and r.cmd is None


def test_skips_meta_sidechain_and_other_types() -> None:
    b = SessionBuilder(REPO)
    b.other("summary", summary="x")
    b.other("attachment")
    b.other("file-history-snapshot")
    b.user("meta", isMeta=True)
    b.user("side", isSidechain=True)
    b.user("real")
    steps = parse(b)
    assert [s.text for s in steps] == ["real"]


def test_sidechain_kept_in_subagent_session() -> None:
    b = SessionBuilder(REPO, sidechain=True)
    b.user("subagent prompt")
    steps = parse_session(b.text().encode(), 1, repo_root=REPO, changed_files=CHANGED, main=False)
    assert [(s.session, s.text) for s in steps] == [(1, "subagent prompt")]


def test_assistant_merge_is_by_message_id_even_if_interleaved() -> None:
    b = SessionBuilder(REPO)
    mid = b.assistant(tool("t1", "Read", file_path=f"{REPO}/auth/session.py"))
    b.result("t1", "contents")
    b.assistant(tool("t2", "Read", file_path=f"{REPO}/reports/export.py"), msg_id=mid)
    b.result("t2", "more")
    steps = parse(b)
    assert [s.role for s in steps] == ["assistant", "tool_result", "tool_result"]
    assert steps[0].tools == ["Read", "Read"]
    assert steps[0].files == ["auth/session.py", "reports/export.py"]
    assert steps[2].files == ["reports/export.py"]


def test_text_blocks_and_tool_results_in_one_user_line() -> None:
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Bash", command="ls"))
    b.user(
        [
            {"type": "tool_result", "tool_use_id": "t1", "content": "a"},
            text("interrupt note"),
            text("second"),
        ]
    )
    steps = parse(b)
    assert [(s.role, s.text) for s in steps[1:]] == [
        ("tool_result", "a"),
        ("user", "interrupt note\nsecond"),
    ]


def test_tool_result_list_content_and_image() -> None:
    png = b"\x89PNG fake"
    img = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(png).decode(),
        },
    }
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Read", file_path="/elsewhere/pic.png"))
    b.result("t1", [text("line1"), img, text("line2")])
    steps = parse(b)
    digest = hashlib.sha256(png).hexdigest()
    assert steps[1].text == f"line1\n[image sha256:{digest}]\nline2"
    assert steps[0].files == ["<external>"]


def test_user_image_block() -> None:
    png = b"img"
    img = {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(png).decode(),
        },
    }
    b = SessionBuilder(REPO)
    b.user([text("look"), img])
    assert parse(b)[0].text == f"look\n[image sha256:{hashlib.sha256(png).hexdigest()}]"


def test_relative_paths_resolve_against_cwd_and_dedupe() -> None:
    b = SessionBuilder(f"{REPO}/auth")
    b.assistant(
        tool("t1", "Read", file_path="session.py"),
        tool("t2", "Edit", file_path=f"{REPO}/auth/session.py", old_string="1", new_string="2"),
        tool("t3", "Grep", pattern="x", path=REPO),
        tool("t4", "NotebookEdit", notebook_path="../nb.ipynb", new_source=""),
    )
    s = parse(b)[0]
    assert s.files == ["auth/session.py", ".", "nb.ipynb"]


def test_bash_mentions_cmd_ok() -> None:
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Bash", command="sed -i 's/3600/86400/' auth/session.py"))
    b.result("t1", "")
    b.assistant(tool("t2", "Bash", command="cd /work/repo && uv run pytest -q"))
    b.result("t2", "Exit code 1\nFAILED tests/test_export.py", is_error=True)
    steps = parse(b)
    assert steps[0].mentions == ["auth/session.py"] and steps[0].cmd == "other"
    assert steps[0].ok is None
    assert steps[1].mentions == ["auth/session.py"]  # C2: results inherit mentions
    assert steps[1].ok is True and steps[1].cmd == "other"
    assert steps[2].cmd == "test" and steps[2].ok is None
    assert steps[3].cmd == "test" and steps[3].ok is False and steps[3].tools == ["Bash"]


def test_step_cmd_priority_across_bash_calls() -> None:
    b = SessionBuilder(REPO)
    b.assistant(
        tool("t1", "Bash", command="ruff check ."),
        tool("t2", "Bash", command="pytest"),
        tool("t3", "Bash", command="make"),
    )
    b.result("t1", "")
    b.result("t2", "")
    b.result("t3", "")
    steps = parse(b)
    assert steps[0].cmd == "test"
    assert [s.cmd for s in steps[1:]] == ["lint", "test", "build"]


def test_mentions_are_sorted_union() -> None:
    b = SessionBuilder(REPO)
    b.assistant(
        tool("t1", "Bash", command="cat reports/export.py"),
        tool("t2", "Bash", command="cat auth/session.py"),
    )
    assert parse(b)[0].mentions == ["auth/session.py", "reports/export.py"]


def test_non_bash_step_has_null_cmd_and_ok() -> None:
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Write", file_path=f"{REPO}/x.py", content="1"))
    b.result("t1", "done", is_error=True)
    steps = parse(b)
    assert steps[1].ok is None and steps[1].cmd is None


def test_tool_result_without_call_has_no_tools() -> None:
    b = SessionBuilder(REPO)
    b.result("missing", "orphan")
    s = parse(b)[0]
    assert s.tools == [] and s.files == [] and s.cmd is None and s.ok is None


def test_float_in_tool_input_is_rendered() -> None:
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "mcp__browser__computer", action="zoom", scale=0.6))
    assert parse(b)[0].text == '[tool mcp__browser__computer] {"action":"zoom","scale":0.6}'


def test_thinking_only_message_is_an_empty_step() -> None:
    b = SessionBuilder(REPO)
    b.assistant(thinking("only"))
    s = parse(b)[0]
    assert s.role == "assistant" and s.text == ""


def test_persisted_output_pointer_is_replaced(tmp_path: Path) -> None:
    tr = tmp_path / "sess" / "tool-results"
    tr.mkdir(parents=True)
    (tr / "abc.txt").write_text("FULL OUTPUT", encoding="utf-8", newline="")
    pointer = (
        f"<persisted-output>\nOutput too large (31.3KB). Full output saved to: "
        f"{tr / 'abc.txt'}\n\nPreview (first 2KB):\nFULL\n</persisted-output>"
    )
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Bash", command="cat big"))
    b.result("t1", pointer)
    read: dict[str, bytes] = {}
    steps = parse(b, tool_results_dir=str(tr), aux_reads=read)
    assert steps[1].text == "FULL OUTPUT"
    assert list(read) == [str(tr / "abc.txt")]


def test_pointer_outside_tool_results_dir_is_not_followed(tmp_path: Path) -> None:
    other = tmp_path / "secret.txt"
    other.write_text("SECRET", encoding="utf-8", newline="")
    pointer = f"<persisted-output>\nFull output saved to: {other}\n</persisted-output>"
    b = SessionBuilder(REPO)
    b.result("t1", pointer)
    steps = parse(b, tool_results_dir=str(tmp_path / "sess" / "tool-results"))
    assert steps[0].text == pointer


def test_partial_last_line_is_not_sealed() -> None:
    b = SessionBuilder(REPO)
    b.user("one")
    data = b.text().encode() + b'{"type":"user","message":{"content":"tw'
    steps = parse_session(data, 0, repo_root=REPO, changed_files=CHANGED)
    assert [s.text for s in steps] == ["one"]


def test_bad_json_line_raises() -> None:
    with pytest.raises(SessionError):
        parse_session(b"{not json}\n", 0, repo_root=REPO, changed_files=CHANGED)


# --- cmd table ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pytest -q", "test"),
        ("python -m pytest", "test"),
        ("python3 -m pytest tests", "test"),
        ("python3.12 -m unittest", "test"),
        ("python3 -X dev -u -m pytest", "test"),
        ("python -c 'import pytest'", "other"),
        ("python script.py -m pytest", "other"),
        ("uv run pytest", "test"),
        ("uv run --frozen pytest -x", "test"),
        ("uv run --project ~/flipside pytest -q t.py", "test"),
        ("uv run --with pytest-cov --python 3.12 python -m pytest", "test"),
        ("uv run -p 3.12 --directory=sub pytest", "test"),
        ("npx --package vitest vitest run", "test"),
        ("uv run --project ~/x ruff check", "lint"),
        ("uv run python -m pytest", "test"),
        ("cd /a && cd b && FOO=1 BAR=2 pytest", "test"),
        ("npm test", "test"),
        ("npx vitest run", "test"),
        ("npx -y jest", "test"),
        ("go test ./...", "test"),
        ("cargo test", "test"),
        ("make test", "test"),
        ("pnpm test", "test"),
        ("yarn test", "test"),
        (".venv/bin/pytest", "test"),
        ("ruff check .", "lint"),
        ("mypy flipside", "lint"),
        ("eslint src", "lint"),
        ("tsc --noEmit", "lint"),
        ("flake8", "lint"),
        ("black --check .", "lint"),
        ("make lint", "lint"),
        ("make", "build"),
        ("make -j4", "build"),
        ("npm run build", "build"),
        ("pnpm build", "build"),
        ("cargo build --release", "build"),
        ("go build", "build"),
        ("docker build .", "build"),
        ("ls -la", "other"),
        ("black .", "other"),
        ("tsc", "other"),
        ("echo pytest", "other"),
        ("", "other"),
        ("pytest 'unbalanced", "test"),
    ],
)
def test_cmd_table(command: str, expected: str) -> None:
    assert classify_cmd(command) == expected


def test_relative_cwd_resolves_against_repo_root() -> None:
    b = SessionBuilder(".")
    b.assistant(tool("t1", "Edit", file_path="auth/session.py", old_string="a", new_string="b"))
    b2 = SessionBuilder("")
    b2.assistant(tool("t1", "Read", file_path="reports/export.py"))
    assert parse(b)[0].files == ["auth/session.py"]
    assert parse(b2)[0].files == ["reports/export.py"]


# --- C14: a Bash call that never ran is not a failed run ---------------------

NEVER_RAN = [
    "The user doesn't want to proceed with this tool use. The tool use was rejected.",
    "Permission to use Bash has been denied.",
    "Permission for this tool use was denied by a hook.",
    "[Request interrupted by user for tool use]",
    "<tool_use_error>InputValidationError: command is required</tool_use_error>",
    "PreToolUse:Bash hook error: [command hook 1]: Blocked by a rule",
]


@pytest.mark.parametrize("out", NEVER_RAN)
@pytest.mark.parametrize("as_list", [False, True])
def test_bash_call_that_never_ran_has_ok_null(out: str, as_list: bool) -> None:
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Bash", command="pytest -q"))
    b.result("t1", [text(out)] if as_list else out, is_error=True)
    r = parse(b)[-1]
    assert r.role == "tool_result" and r.cmd == "test"
    assert r.ok is None


def test_bash_call_that_ran_and_failed_has_ok_false() -> None:
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Bash", command="pytest -q"))
    b.result("t1", "Exit code 1\nFAILED tests/test_x.py::test_a", is_error=True)
    assert parse(b)[-1].ok is False


def test_never_ran_prefix_only_counts_at_the_start() -> None:
    b = SessionBuilder(REPO)
    b.assistant(tool("t1", "Bash", command="pytest -q"))
    b.result("t1", "Exit code 1\n[Request interrupted by user for tool use]", is_error=True)
    assert parse(b)[-1].ok is False


# --- C15: every shell segment counts, wrappers strip, script runners ---------


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("source .venv/bin/activate && pytest -q", "test"),
        (". .venv/bin/activate; pytest", "test"),
        ("git status && pytest", "test"),
        ("set -e; pytest", "test"),
        ("(cd api; pytest)", "test"),
        ("ruff check . && pytest -q", "test"),
        ("pytest -q || true", "test"),
        ("make lint\nmake test", "test"),
        ("ruff check . && npm run build", "lint"),
        ("env FOO=1 pytest", "test"),
        ("env -u HOME pytest", "test"),
        ("timeout 60 pytest", "test"),
        ("timeout -s KILL 5m npm test", "test"),
        ("time pytest", "test"),
        ("nice -n 10 cargo test", "test"),
        ("exec pytest", "test"),
        ("command pytest", "test"),
        ("npm run test", "test"),
        ("npm run test:unit", "test"),
        ("pnpm run test", "test"),
        ("yarn run test", "test"),
        ("bun test", "test"),
        ("bun run test", "test"),
        ("npm run lint", "lint"),
        ("pnpm lint", "lint"),
        ("yarn lint", "lint"),
        ("pnpm run build", "build"),
        ("yarn build", "build"),
        ("bun run build", "build"),
        ("echo 'pytest && ruff'", "other"),
        ('git commit -m "run pytest; fix"', "other"),
        ("npm run testimony", "other"),
        ("cat <<EOF > notes.md\npytest\nEOF", "other"),
        ("cat <<'EOF' > notes.md\npytest\nEOF\nruff check .", "lint"),
    ],
)
def test_cmd_segments_wrappers_and_scripts(command: str, expected: str) -> None:
    assert classify_cmd(command) == expected
