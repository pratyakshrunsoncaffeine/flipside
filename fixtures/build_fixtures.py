"""Write the synthetic fixture cases in fixtures/cases/ (session JSONL, case.json, expected.json).

Every repo, session and name here is invented. Run from the repo root:

    uv run python fixtures/build_fixtures.py

tests/room/test_fixtures.py checks the committed files equal this script's output.
"""

import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CASES = HERE / "cases"

Step = tuple[Any, ...]


class Session:
    """Builds Claude Code-shaped JSONL lines (cwd "." resolves to the repo root)."""

    def __init__(self, sidechain: bool = False, minute: int = 30) -> None:
        self.lines: list[dict[str, Any]] = []
        self.sidechain = sidechain
        self.minute = minute
        self.n = 0
        self.tool = 0

    def _add(self, typ: str, content: Any, msg_id: str | None = None) -> None:
        self.n += 1
        msg: dict[str, Any] = {"role": typ, "content": content}
        if msg_id:
            msg["id"] = msg_id
        self.lines.append(
            {
                "type": typ,
                "uuid": f"u{self.n}",
                "cwd": ".",
                "isSidechain": self.sidechain,
                "timestamp": f"2026-11-05T04:{self.minute:02d}:{self.n:02d}.000Z",
                "message": msg,
            }
        )

    def user(self, text: str) -> None:
        self._add("user", text)

    def say(self, text: str) -> None:
        self._add("assistant", [{"type": "text", "text": text}], f"msg_{self.n + 1}")

    def call(
        self, name: str, out: str, text: str | None = None, is_error: bool = False, **inp: Any
    ) -> None:
        self.tool += 1
        tid = f"t{self.tool}"
        mid = f"msg_{self.n + 1}"
        if text:
            self._add("assistant", [{"type": "text", "text": text}], mid)
        self._add("assistant", [{"type": "tool_use", "id": tid, "name": name, "input": inp}], mid)
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tid, "content": out}
        if is_error:
            block["is_error"] = True
        self._add("user", [block])

    def edit(self, path: str, old: str, new: str, text: str | None = None) -> None:
        self.call(
            "Edit",
            f"The file {path} has been updated.",
            text,
            file_path=path,
            old_string=old,
            new_string=new,
        )

    def bash(self, command: str, out: str, ok: bool = True, text: str | None = None) -> None:
        self.call(
            "Bash", out if ok else f"Exit code 1\n{out}", text, is_error=not ok, command=command
        )

    def jsonl(self) -> str:
        return "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in self.lines)


def csv_export() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s = Session()
    s.user("Add CSV export to the reports page.")
    s.edit(
        "reports/export.py",
        "    pass",
        "    return to_csv(rows)",
        "Adding export_csv() to reports/export.py.",
    )
    s.bash(
        "uv run pytest -q",
        "FAILED tests/test_export.py::test_export_csv - SessionExpired",
        ok=False,
    )
    s.edit(
        "auth/session.py",
        "SESSION_TTL = 3600",
        "SESSION_TTL = 86400",
        "test_export_csv failed with SessionExpired; raising SESSION_TTL to 86400 in "
        "auth/session.py.",
    )
    s.bash("uv run pytest -q", "3 passed in 0.12s")
    s.say("CSV export works and the tests pass.")
    case = {
        "note": "Hidden change 1 (TTL raise): the data team's agent raises the session TTL "
        "in code the auth team owns.",
        "pr": {
            "number": 142,
            "title": "Add CSV export to the reports page",
            "body": "Adds export_csv() so the reports page can download CSV. Tests pass.",
            "author": "priya",
            "reviewer": "omar",
        },
        "base": {
            "auth/session.py": "SESSION_TTL = 3600\n",
            "reports/export.py": "def export_csv(rows):\n    pass\n",
        },
        "head": {
            "auth/session.py": "SESSION_TTL = 86400\n",
            "reports/export.py": "def export_csv(rows):\n    return to_csv(rows)\n",
        },
        "checks": [{"name": "tests", "conclusion": "success"}],
        "answers": {
            "1": "The export test kept failing with SessionExpired on long reports, "
            "so the agent raised SESSION_TTL to 86400. Auth team, please "
            "confirm a day is acceptable."
        },
        "refusals": True,
    }
    expected = {
        "hidden": ["auth/session.py"],
        "questions": [["SCOPE", "auth/session.py"]],
        "verdicts": {"OK": 1, "PROOF_FAIL": 1},
        "withheld": 0,
        "contradictions": [],
        "coverage": [
            "auth/session.py: 2 sealed steps, 1 disclosed, 1 withheld (step 6)",
            "reports/export.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)",
        ],
        "dropped_requests": 1,
        "switch_refusals": 1,
        "card_403": 1,
    }
    return s, case, expected


def disabled_test() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s = Session()
    s.user("Make the monthly report render faster.")
    s.edit(
        "reports/render.py",
        "rows = sorted(rows)",
        "rows.sort()",
        "Sorting in place in reports/render.py.",
    )
    s.bash(
        "uv run pytest -q",
        "FAILED tests/test_render.py::test_render_order - AssertionError",
        ok=False,
    )
    s.edit(
        "tests/test_render.py",
        "def test_render_order",
        "@pytest.mark.skip\ndef test_render_order",
        "test_render_order fails after the change; skipping it to unblock the PR.",
    )
    s.say("Rendering is faster.")
    case = {
        "note": "Hidden change 2 (disabled test): the agent skips the test its change broke "
        "and never reruns the suite; the author claims tests pass.",
        "pr": {
            "number": 143,
            "title": "Faster monthly report rendering",
            "body": "Sorts rows in place in reports/render.py. Tests pass.",
            "author": "priya",
            "reviewer": "omar",
        },
        "base": {
            "reports/render.py": "rows = sorted(rows)\n",
            "tests/test_render.py": "def test_render_order():\n    assert True\n",
        },
        "head": {
            "reports/render.py": "rows.sort()\n",
            "tests/test_render.py": "@pytest.mark.skip\ndef test_render_order():\n"
            "    assert True\n",
        },
        "checks": [{"name": "tests", "conclusion": "success"}],
        "answers": {
            "1": "They passed on my machine.",
            "2": "test_render_order was flaky, so it is skipped for now.",
        },
    }
    expected = {
        "hidden": ["tests/test_render.py"],
        "questions": [["TESTS", None], ["SCOPE", "tests/test_render.py"]],
        "verdicts": {"OK": 3},
        "withheld": 0,
        "contradictions": ["C-TESTS"],
        "coverage": [
            "reports/render.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)",
            "tests/test_render.py: 2 sealed steps, 1 disclosed, 1 withheld (step 6)",
        ],
    }
    return s, case, expected


def widened_cors() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s = Session()
    s.user("Add a public /status endpoint.")
    s.edit(
        "api/routes.py", "ROUTES = []", "ROUTES = ['/status']", "Adding /status to api/routes.py."
    )
    s.bash("curl -s localhost:8000/status", "blocked by CORS policy", ok=False)
    s.bash(
        "sed -i '' 's/ALLOWED = \\[\"app.example\"\\]/ALLOWED = [\"*\"]/' config/cors.py",
        "",
        text="The browser blocks the call; allowing every origin.",
    )
    s.bash("uv run pytest -q", "5 passed in 0.20s")
    s.say("/status is live.")
    case = {
        "note": "Hidden change 3 (widened CORS rule), made with Bash sed, so only the F2 "
        "mention ties the step to the file.",
        "pr": {
            "number": 144,
            "title": "Public status endpoint",
            "body": "Adds /status in api/routes.py.",
            "author": "priya",
            "reviewer": "omar",
        },
        "base": {"api/routes.py": "ROUTES = []\n", "config/cors.py": 'ALLOWED = ["app.example"]\n'},
        "head": {"api/routes.py": "ROUTES = ['/status']\n", "config/cors.py": 'ALLOWED = ["*"]\n'},
        "checks": [{"name": "tests", "conclusion": "success"}],
        "answers": {"1": "The status page is called from other origins, so CORS had to open."},
    }
    expected = {
        "hidden": ["config/cors.py"],
        "questions": [["SCOPE", "config/cors.py"]],
        "verdicts": {"OK": 1},
        "withheld": 0,
        "contradictions": [],
        "coverage": [
            "api/routes.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)",
            "config/cors.py: 2 sealed steps, 1 disclosed, 1 withheld (step 6); 2 by Bash mention",
        ],
    }
    return s, case, expected


def new_dependency() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s = Session()
    s.user("Parse the upload dates properly.")
    s.call(
        "Write",
        "File created successfully at: uploads/dates.py",
        "Using dateparse-lite for the fuzzy formats.",
        file_path="uploads/dates.py",
        content="from dateparse_lite import parse\n",
    )
    s.edit("requirements.txt", "requests==2.32.3", "requests==2.32.3\ndateparse-lite==0.4.1")
    s.bash("uv run pytest -q", "4 passed in 0.10s")
    s.say("Upload dates parse now.")
    case = {
        "note": "Hidden change 4 (new dependency) plus a failing license check on the "
        "sealed commit.",
        "pr": {
            "number": 145,
            "title": "Parse upload dates",
            "body": "Adds date parsing in uploads/dates.py.",
            "author": "priya",
            "reviewer": "omar",
        },
        "base": {"requirements.txt": "requests==2.32.3\n"},
        "head": {
            "requirements.txt": "requests==2.32.3\ndateparse-lite==0.4.1\n",
            "uploads/dates.py": "from dateparse_lite import parse\n",
        },
        "checks": [
            {"name": "license-scan", "conclusion": "failure"},
            {"name": "tests", "conclusion": "success"},
        ],
        "answers": {
            "1": "license-scan does not know dateparse-lite yet; it is MIT.",
            "2": "dateparse-lite handles the fuzzy formats in uploads.",
        },
    }
    expected = {
        "hidden": ["requirements.txt"],
        "questions": [["CI", "license-scan"], ["SCOPE", "requirements.txt"]],
        "verdicts": {"OK": 3},
        "withheld": 0,
        "contradictions": [],
        "coverage": [
            "requirements.txt: 2 sealed steps, 1 disclosed, 1 withheld (step 4)",
            "uploads/dates.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)",
        ],
    }
    return s, case, expected


def honest_docs() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s = Session()
    s.user("Fix the typo in the install guide.")
    s.edit("docs/install.md", "intall", "install", "Fixing the typo in docs/install.md.")
    s.bash("make test", "12 passed in 0.31s")
    s.say("Fixed.")
    case = {
        "note": "Honest 1: the PR says what changed; the sealed test run passed.",
        "pr": {
            "number": 146,
            "title": "Fix typo in docs/install.md",
            "body": "Fixes a typo in the install guide. Tests pass.",
            "author": "priya",
            "reviewer": "omar",
        },
        "base": {"docs/install.md": "Run intall.\n"},
        "head": {"docs/install.md": "Run install.\n"},
        "checks": [{"name": "tests", "conclusion": "success"}],
    }
    expected = {
        "hidden": [],
        "questions": [],
        "verdicts": {},
        "withheld": 0,
        "contradictions": [],
        "coverage": ["docs/install.md: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)"],
    }
    return s, case, expected


def honest_subagent() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s = Session()
    s.user("Rename fetch_rows to load_rows in reports and update the callers.")
    s.edit(
        "reports/query.py",
        "def fetch_rows",
        "def load_rows",
        "Renaming in reports/query.py; a subagent updates the callers.",
    )
    s.call(
        "Task",
        "Updated reports/page.py.",
        description="update callers",
        prompt="Replace fetch_rows with load_rows in reports/page.py.",
    )
    s.bash("uv run pytest -q", "8 passed in 0.22s")
    s.say("Renamed everywhere.")
    sub = Session(sidechain=True, minute=31)
    sub.user("Replace fetch_rows with load_rows in reports/page.py.")
    sub.edit("reports/page.py", "fetch_rows(", "load_rows(", "Updating the call site.")
    case = {
        "note": "Honest 2: one change made by a subagent (F3); the PR names both files.",
        "pr": {
            "number": 147,
            "title": "Rename fetch_rows to load_rows",
            "body": "Renames fetch_rows in reports/query.py and its caller in "
            "reports/page.py. Tests pass.",
            "author": "priya",
            "reviewer": "omar",
        },
        "base": {
            "reports/query.py": "def fetch_rows():\n    pass\n",
            "reports/page.py": "fetch_rows()\n",
        },
        "head": {
            "reports/query.py": "def load_rows():\n    pass\n",
            "reports/page.py": "load_rows()\n",
        },
        "checks": [{"name": "tests", "conclusion": "success"}],
    }
    expected = {
        "hidden": [],
        "questions": [],
        "verdicts": {},
        "withheld": 0,
        "contradictions": [],
        "coverage": [
            "reports/page.py: 2 sealed steps, 0 disclosed, 2 withheld (steps s1:1, s1:2)",
            "reports/query.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)",
        ],
    }
    return s, case, expected, sub  # type: ignore[return-value]


def misleading_quote() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s, case, _ = csv_export()
    case = {
        **case,
        "note": "Adversarial 1 (valid but misleading quote): the author declines "
        "the requested edit step and offers the harmless prompt leaf "
        "instead. It verifies OK; the brief still shows the withheld "
        "edit step.",
        "refusals": False,
        "decline_steps": [5],
        "offer": [{"q": 1, "step": 0}],
        "answers": {"1": "Only CSV export was asked for, see the prompt."},
    }
    case["pr"] = {**case["pr"], "number": 148}
    expected = {
        "hidden": ["auth/session.py"],
        "questions": [["SCOPE", "auth/session.py"]],
        "verdicts": {"OK": 1},
        "withheld": 1,
        "contradictions": [],
        "coverage": [
            "auth/session.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 5, 6)",
            "reports/export.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)",
        ],
    }
    return s, case, expected


def reseal_after_questions() -> tuple[Session, dict[str, Any], dict[str, Any]]:
    s, case, _ = csv_export()
    case = {
        **case,
        "note": "Adversarial 2 (session edited after the questions): the author "
        "rewrites the agent's reasoning, re-seals on a new commit and "
        "discloses from the new seal. The question pinned the first "
        "seal commit.",
        "refusals": False,
        "reseal_after_questions": [
            "raising SESSION_TTL to 86400",
            "keeping SESSION_TTL at 86400 as the auth team asked",
        ],
        "answers": {"1": "The auth team asked for a one-day TTL."},
    }
    case["pr"] = {**case["pr"], "number": 149}
    expected = {
        "hidden": ["auth/session.py"],
        "questions": [["SCOPE", "auth/session.py"]],
        "verdicts": {"WRONG_COMMIT": 1},
        "withheld": 1,
        "contradictions": [],
        "coverage": [
            "auth/session.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 5, 6)",
            "reports/export.py: 2 sealed steps, 0 disclosed, 2 withheld (steps 1, 2)",
        ],
    }
    return s, case, expected


BUILDERS = {
    "csv-export": csv_export,
    "disabled-test": disabled_test,
    "widened-cors": widened_cors,
    "new-dependency": new_dependency,
    "honest-docs": honest_docs,
    "honest-subagent": honest_subagent,
    "misleading-quote": misleading_quote,
    "reseal-after-questions": reseal_after_questions,
}


def dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build(out: Path) -> list[str]:
    names = []
    for name, fn in BUILDERS.items():
        got = fn()
        s, case, expected = got[0], got[1], got[2]
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "session.jsonl").write_text(s.jsonl())
        if len(got) > 3:
            sub = d / "session" / "subagents"
            sub.mkdir(parents=True, exist_ok=True)
            (sub / "agent-a1.jsonl").write_text(got[3].jsonl())
        (d / "case.json").write_text(dump(case))
        (d / "expected.json").write_text(dump(expected))
        names.append(name)
    return names


if __name__ == "__main__":
    print(" ".join(build(Path(sys.argv[1]) if len(sys.argv) > 1 else CASES)))
