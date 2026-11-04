"""`tools/board` against a fake `gh`, including two agents sharing one GitHub login."""

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BOARD = Path(__file__).resolve().parents[1] / "tools" / "board"

FAKE_GH = """#!/usr/bin/env bash
[ "$1" = api ] || exit 1; shift
[ "$1" = --paginate ] && shift
path="$1"; shift
case "$path" in
  user) cat "$FAKE_GH/login" ;;
  */comments*)
    if [ "${1:-}" = -f ]; then printf '%s\\n' "${2#body=}" >> "$FAKE_GH/posted"; echo https://x/1
    else cat "$FAKE_GH/rows"; fi ;;
  */issues/*) wc -l < "$FAKE_GH/rows" | tr -d ' ' ;;
  repos/*) echo "${path#repos/}" ;;
esac
"""


def find_bash() -> str | None:
    if sys.platform != "win32":
        return shutil.which("bash")
    # The bash.exe on PATH may be WSL, which sees paths differently; use the one beside git.
    git = shutil.which("git")
    if git is None:
        return None
    # git.exe sits in Git\cmd, Git\bin or Git\mingw64\bin depending on the install.
    for root in Path(git).resolve().parents[:3]:
        for bash in (root / "bin" / "bash.exe", root / "usr" / "bin" / "bash.exe"):
            if bash.exists():
                return str(bash)
    return None


BASH = find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash (Git Bash on Windows)")


@pytest.fixture
def board(tmp_path):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "gh").write_text(FAKE_GH, newline="\n")
    (fake / "gh").chmod(0o755)
    (fake / "login").write_text("pratyaksh\n")
    (fake / "rows").write_text("")
    work = tmp_path / "work"
    work.mkdir()

    def comments(*posts: tuple[str, str]) -> None:
        rows = [
            f"{i}\t{login}\t2026-11-04T10:00:0{i}Z\t{base64.b64encode(body.encode()).decode()}"
            for i, (login, body) in enumerate(posts, start=1)
        ]
        (fake / "rows").write_text("".join(row + "\n" for row in rows), newline="\n")

    def run(*args: str, **env: str) -> subprocess.CompletedProcess:
        full_env = {**os.environ, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_GH": fake.as_posix(), "BOARD_REPO": "o/r",
                    # pytest's basetemp is inside this repo; keep board state in `work`.
                    "GIT_CEILING_DIRECTORIES": tmp_path.as_posix(), **env}
        for key in ("BOARD_SIGN", "BOARD_HANDLE", "BOARD_LOGIN", "BOARD_ISSUE"):
            if key not in env:
                full_env.pop(key, None)
        return subprocess.run([BASH, BOARD.as_posix(), *args], cwd=work, env=full_env,
                              capture_output=True, text=True, timeout=30)

    run.comments = comments
    run.posted = lambda: (fake / "posted").read_text().splitlines()
    return run


CODEX = {"BOARD_SIGN": "Pratyaksh's Codex", "BOARD_HANDLE": "pratyaksh-codex"}
CLAUDE = {"BOARD_SIGN": "Pratyaksh's Claude", "BOARD_HANDLE": "pratyaksh-claude"}


def test_without_a_sign_your_own_login_is_hidden(board):
    board.comments(
        ("pratyaksh", "[Pratyaksh's Claude] mine"),
        ("kadoo69", "[Aarav's Claude] @pratyaksh hi"),
    )

    out = board("unread").stdout

    assert "mine" not in out
    assert "@pratyaksh hi" in out
    assert "** MENTION **" in out


def test_two_agents_on_one_login_see_each_other(board):
    board.comments(
        ("pratyaksh", "[Pratyaksh's Claude] @pratyaksh-codex take the author agent"),
        ("pratyaksh", "[Pratyaksh's Codex] done with fixtures"),
    )

    codex = board("unread", **CODEX).stdout
    claude = board("unread", **CLAUDE).stdout

    assert "take the author agent" in codex
    assert "** MENTION **" in codex
    assert "done with fixtures" not in codex
    assert "done with fixtures" in claude
    assert "take the author agent" not in claude


def test_post_must_carry_the_agents_own_sign(board):
    wrong = board("post", "[Pratyaksh's Claude] hi", **CODEX)
    right = board("post", "[Pratyaksh's Codex] hi", **CODEX)

    assert wrong.returncode != 0
    assert "BOARD_SIGN" in wrong.stderr
    assert right.returncode == 0
    assert board.posted() == ["[Pratyaksh's Codex] hi"]


def test_a_bad_handle_is_refused(board):
    result = board("unread", BOARD_HANDLE="no spaces")

    assert result.returncode != 0
    assert "BOARD_HANDLE" in result.stderr
