"""Seal: key, salts, leaves, manifest, trailer commit and local state."""

import hashlib
import hmac
import json
import stat
from pathlib import Path

import pytest

from flipside.seal.canon import canon
from flipside.seal.git import parse_trailer, trailer_values
from flipside.seal.manifest import load_manifest
from flipside.seal.seal import SealError, build_leaves, project_dir_name, salt_for, seal
from flipside.seal.steps import Step
from tests.seal.builder import SessionBuilder, tool
from tests.seal.conftest import PR, run

KEY = bytes(32)


def test_salt_formula() -> None:
    want = hmac.new(KEY, b"flipside/salt/v1" + b"[0,3,1]", hashlib.sha256).digest()
    assert salt_for(KEY, 0, 3, 1) == want


def test_empty_session_refuses() -> None:
    with pytest.raises(SealError, match="EMPTY_SESSION"):
        build_leaves([], KEY)


def test_key_must_be_32_bytes() -> None:
    with pytest.raises(SealError):
        build_leaves([Step(0, 0, "user", text="x")], b"short")


def test_leaves_in_session_step_chunk_order_and_manifest_has_no_text() -> None:
    steps = [
        Step(1, 0, "user", text="sub"),
        Step(0, 0, "user", text="a " * 200),
        Step(0, 1, "assistant", text=""),
    ]
    s = build_leaves(steps, KEY)
    assert [(lf["session"], lf["step"], lf["chunk"]) for lf in s.leaves] == [
        (0, 0, 0),
        (0, 0, 1),
        (0, 1, 0),
        (1, 0, 0),
    ]
    entries = load_manifest(s.manifest)
    assert [e["i"] for e in entries] == [0, 1, 2, 3]
    assert all("text" not in e for e in entries)
    assert b"sub" not in s.manifest
    assert s.manifest == canon(entries)


def test_seal_commit_trailer_state_and_key_mode(pr: PR) -> None:
    res = seal(pr.repo, pr.session, "main")
    assert res.commit is not None
    msg = run(pr.repo, "show", "-s", "--format=%B", "HEAD")
    assert msg.startswith("flipside: seal session\n")
    values = trailer_values(pr.repo, res.commit)
    assert len(values) == 1
    t = parse_trailer(values[0])
    assert t == res.sealed.trailer
    assert run(pr.repo, "diff", "--name-only", "HEAD~1", "HEAD") == ""
    assert stat.S_IMODE(res.key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(res.state_path.stat().st_mode) == 0o600
    assert res.key_path.parent == pr.repo / ".git" / "flipside"
    state = json.loads(res.state_path.read_text(encoding="utf-8"))
    assert state["commit"] == res.commit and state["changed_files"] == [
        "auth/session.py",
        "reports/export.py",
    ]
    assert state["sessions"][0]["length"] == pr.session.stat().st_size
    assert res.manifest_path.read_bytes() == res.sealed.manifest
    assert b"86400" not in res.sealed.manifest
    assert "86400" not in res.state_path.read_text(encoding="utf-8")


def test_same_key_same_root_new_key_new_root(pr: PR) -> None:
    a = seal(pr.repo, pr.session, "main", key=KEY, commit=False)
    b = seal(pr.repo, pr.session, "main", key=KEY, commit=False)
    c = seal(pr.repo, pr.session, "main", commit=False)
    assert a.sealed.root == b.sealed.root
    assert a.sealed.manifest == c.sealed.manifest
    assert a.sealed.root != c.sealed.root


def test_staged_changes_refuse(pr: PR) -> None:
    (pr.repo / "new.txt").write_text("x", encoding="utf-8", newline="")
    run(pr.repo, "add", "new.txt")
    with pytest.raises(SealError, match="staged"):
        seal(pr.repo, pr.session, "main")


def test_bad_base_refuses(pr: PR) -> None:
    with pytest.raises(SealError, match="base"):
        seal(pr.repo, pr.session, "origin/nope", commit=False)


def test_amend_adds_trailer_to_head(pr: PR) -> None:
    before = run(pr.repo, "rev-list", "--count", "HEAD")
    res = seal(pr.repo, pr.session, "main", amend=True)
    assert run(pr.repo, "rev-list", "--count", "HEAD") == before
    assert res.commit and len(trailer_values(pr.repo, res.commit)) == 1
    assert run(pr.repo, "diff", "--name-only", "main", "HEAD").split() == [
        "auth/session.py",
        "reports/export.py",
    ]


def test_metadata_of_csv_session(pr: PR) -> None:
    res = seal(pr.repo, pr.session, "main", commit=False)
    m = load_manifest(res.sealed.manifest)
    tests = [e for e in m if e["cmd"] == "test" and e["role"] == "tool_result"]
    assert [e["ok"] for e in tests] == [False, True]
    edits = [e for e in m if "Edit" in e["tools"] and e["role"] == "assistant" and e["chunk"] == 0]
    assert [e["files"] for e in edits] == [["reports/export.py"], ["auth/session.py"]]


def test_g7_subagent_is_session_1_and_sorted(pr: PR, tmp_path: Path) -> None:
    """G7 (F3): subagent transcripts seal as sessions 1..k, by first timestamp then name."""
    sub = pr.session.with_suffix("") / "subagents"
    late = SessionBuilder(str(pr.repo), sidechain=True, start=50)
    late.user("late subagent")
    early = SessionBuilder(str(pr.repo), sidechain=True, start=5)
    early.user("early subagent")
    early.assistant(
        tool("s1", "Edit", file_path=f"{pr.repo}/auth/session.py", old_string="a", new_string="b")
    )
    late.write(sub / "agent-aaa.jsonl")
    early.write(sub / "agent-zzz.jsonl")
    res = seal(pr.repo, pr.session, "main", commit=False)
    m = load_manifest(res.sealed.manifest)
    s1 = [e for e in m if e["session"] == 1]
    s2 = [e for e in m if e["session"] == 2]
    assert s1[1]["files"] == ["auth/session.py"]
    assert [lf["text"] for lf in res.sealed.leaves if lf["session"] == 2] == ["late subagent"]
    assert len(s2) == 1


def test_g7_bash_sed_mention(pr: PR) -> None:
    """G7 (F2): a Bash sed -i on a changed file shows in mentions."""
    b = pr.builder
    b.assistant(tool("t9", "Bash", command="sed -i '' 's/3600/86400/' auth/session.py"))
    b.result("t9", "")
    b.write(pr.session)
    m = load_manifest(seal(pr.repo, pr.session, "main", commit=False).sealed.manifest)
    sed = [e for e in m if e["mentions"]]
    assert [(e["role"], e["mentions"], e["cmd"]) for e in sed] == [
        ("assistant", ["auth/session.py"], "other"),
        ("tool_result", ["auth/session.py"], "other"),
    ]


def test_project_dir_name() -> None:
    assert project_dir_name(Path("/Users/a.b/flip_side")) == "-Users-a-b-flip-side"


def test_unchanged_text_in_leaf() -> None:
    s = build_leaves([Step(0, 0, "assistant", ["Edit"], ["a.py"], text="x")], KEY)
    assert s.leaves[0] == {
        "v": 1,
        "session": 0,
        "step": 0,
        "chunk": 0,
        "role": "assistant",
        "tools": ["Edit"],
        "files": ["a.py"],
        "mentions": [],
        "cmd": None,
        "ok": None,
        "text": "x",
    }


def test_seal_from_session_with_partial_last_line(pr: PR) -> None:
    with pr.session.open("ab") as fh:
        fh.write(b'{"type":"user","message":{"content":"half')
    res = seal(pr.repo, pr.session, "main", commit=False)
    state = json.loads(res.state_path.read_text(encoding="utf-8"))
    assert state["sessions"][0]["length"] == len(pr.builder.text().encode())
    assert all("half" not in lf["text"] for lf in res.sealed.leaves)


def test_csv_session_has_ten_steps(pr: PR) -> None:
    res = seal(pr.repo, pr.session, "main", commit=False)
    steps = {(lf["session"], lf["step"]) for lf in res.sealed.leaves}
    assert len(steps) == 10
    assert [lf["role"] for lf in res.sealed.leaves][:3] == ["user", "assistant", "tool_result"]
