"""Rebuild the offline G8 example: a sealed CSV-export PR, one honest and one forged quote.

Everything is synthetic. The seal uses the demo key (32 zero bytes) and a fixed git
identity and clock, so the seal commit hash is the same on every machine.

    uv run python examples/build.py [out_dir]     # default: examples/
    flip verify --bundle examples/seal.bundle --commit $(cat examples/commit.txt) \\
        --manifest examples/manifest.json examples/q2-ok.json
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from flipside.seal.canon import canon
from flipside.seal.prove import prove
from flipside.seal.seal import seal

HERE = Path(__file__).resolve().parent
DEMO_KEY = bytes(32)
GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "Demo Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Demo Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
    "GIT_AUTHOR_DATE": "2026-11-05T10:00:00+05:30",
    "GIT_COMMITTER_DATE": "2026-11-05T10:00:00+05:30",
}


def session_lines() -> list[dict[str, Any]]:
    """A data team's agent adds CSV export and quietly raises the session TTL."""
    lines: list[dict[str, Any]] = []

    def add(typ: str, content: Any, msg_id: str | None = None) -> None:
        n = len(lines) + 1
        msg: dict[str, Any] = {"role": typ, "content": content}
        if msg_id:
            msg["id"] = msg_id
        lines.append(
            {
                "type": typ,
                "uuid": f"u{n}",
                "cwd": ".",
                "isSidechain": False,
                "timestamp": f"2026-11-05T04:30:{n:02d}.000Z",
                "message": msg,
            }
        )

    def call(tid: str, name: str, msg_id: str, **inp: Any) -> None:
        add("assistant", [{"type": "tool_use", "id": tid, "name": name, "input": inp}], msg_id)

    def result(tid: str, text: str, is_error: bool = False) -> None:
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tid, "content": text}
        if is_error:
            block["is_error"] = True
        add("user", [block])

    add("user", "Add CSV export to the reports page.")
    add(
        "assistant",
        [{"type": "text", "text": "Adding export_csv() to reports/export.py."}],
        "msg_1",
    )
    call(
        "t1",
        "Edit",
        "msg_1",
        file_path="reports/export.py",
        old_string="    pass",
        new_string="    return to_csv(rows)",
    )
    result("t1", "The file reports/export.py has been updated.")
    call("t2", "Bash", "msg_2", command="uv run pytest -q")
    result(
        "t2",
        "Exit code 1\nFAILED tests/test_export.py::test_export_csv - SessionExpired",
        is_error=True,
    )
    add(
        "assistant",
        [
            {
                "type": "text",
                "text": "test_export_csv failed with SessionExpired; "
                "raising SESSION_TTL to 86400 in auth/session.py.",
            }
        ],
        "msg_3",
    )
    call(
        "t3",
        "Edit",
        "msg_3",
        file_path="auth/session.py",
        old_string="SESSION_TTL = 3600",
        new_string="SESSION_TTL = 86400",
    )
    result("t3", "The file auth/session.py has been updated.")
    call("t4", "Bash", "msg_4", command="uv run pytest -q")
    result("t4", "3 passed in 0.12s")
    add("assistant", [{"type": "text", "text": "CSV export works and the tests pass."}], "msg_5")
    return lines


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def build(out: Path) -> dict[str, Any]:
    os.environ.update(GIT_ENV)
    with tempfile.TemporaryDirectory(prefix="flip-example-") as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "auth").mkdir()
        (repo / "reports").mkdir()
        (repo / "auth" / "session.py").write_text(
            "SESSION_TTL = 3600\n", encoding="utf-8", newline=""
        )
        (repo / "reports" / "export.py").write_text(
            "def export_csv(rows):\n    pass\n", encoding="utf-8", newline=""
        )
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "Reports page")
        git(repo, "checkout", "-q", "-b", "csv-export")
        (repo / "auth" / "session.py").write_text(
            "SESSION_TTL = 86400\n", encoding="utf-8", newline=""
        )
        (repo / "reports" / "export.py").write_text(
            "def export_csv(rows):\n    return to_csv(rows)\n", encoding="utf-8", newline=""
        )
        git(repo, "commit", "-q", "-am", "Add CSV export to the reports page")

        session_text = "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in session_lines())
        session = Path(tmp) / "claude" / "session.jsonl"
        session.parent.mkdir()
        session.write_text(session_text, encoding="utf-8", newline="")
        res = seal(repo, session, "main", key=DEMO_KEY)
        assert res.commit
        leaves = res.sealed.leaves
        i = next(
            k
            for k, lf in enumerate(leaves)
            if lf["role"] == "assistant"
            and "auth/session.py" in lf["files"]
            and "86400" in lf["text"]
        )
        ok = prove(repo, res.sealed.root.hex(), i)
        forged = copy.deepcopy(ok)
        forged["leaf"]["text"] = forged["leaf"]["text"].replace("86400", "3600")

        out.mkdir(parents=True, exist_ok=True)
        (out / "session.jsonl").write_text(session_text, encoding="utf-8", newline="")
        (out / "manifest.json").write_bytes(res.sealed.manifest)
        (out / "q2-ok.json").write_bytes(canon(ok) + b"\n")
        (out / "q2-forged.json").write_bytes(canon(forged) + b"\n")
        (out / "commit.txt").write_text(res.commit + "\n", encoding="utf-8", newline="")
        bundle = out / "seal.bundle"
        bundle.unlink(missing_ok=True)
        git(repo, "bundle", "create", "-q", str(bundle), "HEAD", "csv-export", "main")
        return {"commit": res.commit, "root": res.sealed.root.hex(), "n": res.sealed.n, "i": i}


if __name__ == "__main__":
    info = build(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE)
    print(json.dumps(info))
