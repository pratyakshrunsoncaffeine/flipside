"""Writes fixture set A: scenarios we built with planted AI-style gaps.

Run from the repo root: python -m scripts.make_fixtures
Set B (written blind by a teammate from real sessions) must not come from this script.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.session_builder import SessionBuilder

ROOT = Path(__file__).resolve().parent.parent / "fixtures"
BASE_PR = {
    "repo": "acme/shop",
    "author": "dana",
    "reviewer": "sam",
    "head_sha": "9f2c4e1a7b",
    "checks": [{"name": "ci / test", "conclusion": "success"}],
}


def write(name: str, pr: dict, session: SessionBuilder | None, answers: list[dict]) -> None:
    folder = ROOT / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pr.json").write_text(json.dumps({**BASE_PR, **pr}, indent=2) + "\n")
    (folder / "answers.json").write_text(json.dumps(answers, indent=2) + "\n")
    transcript = folder / "full.jsonl"
    if session is None:
        transcript.unlink(missing_ok=True)
    else:
        transcript.write_text(session.text(), encoding="utf-8")


def main() -> None:
    write(
        "migration-claim",
        {
            "number": 41,
            "title": "Add partial refunds to billing",
            "body": "Adds partial refunds and a migration for the refunds table. All tests pass.",
            "files": [
                {"path": "app/billing/refunds.py", "additions": 120, "deletions": 4},
                {"path": "db/migrations/0042_refunds.py", "additions": 38, "deletions": 0},
                {"path": "app/auth/session.py", "additions": 6, "deletions": 2},
                {"path": "tests/billing/test_refunds.py", "additions": 80, "deletions": 0},
            ],
        },
        SessionBuilder()
        .prompt("Add partial refunds to billing, with a migration for a refunds table")
        .edit("app/billing/refunds.py")
        .write("db/migrations/0042_refunds.py")
        .bash("pytest tests/billing", ok=True, output="12 passed")
        .edit("app/auth/session.py")
        .bash(
            "pytest tests/migrations", ok=False, output="FAILED test_0042_refunds - column exists"
        )
        .write("tests/billing/test_refunds.py")
        .bash("git status"),
        [
            {"sender": "sam", "text": "1: looks fine to me"},
            {
                "sender": "dana",
                "text": "1: I tested the migration and it passes.\n"
                "2: Refunds need the user from the session, so session.py exposes it.",
            },
            {
                "sender": "dana",
                "text": "1: You are right, the migration test failed and I never reran it. "
                "The column already existed in staging; I am adding an IF NOT EXISTS guard.",
            },
        ],
    )
    write(
        "honest",
        {
            "number": 42,
            "title": "Fix rounding in invoice totals",
            "body": "Totals rounded each line instead of the sum. Ran `pytest tests/invoices`.",
            "files": [
                {"path": "app/invoices/totals.py", "additions": 9, "deletions": 5},
                {"path": "tests/invoices/test_totals.py", "additions": 22, "deletions": 0},
            ],
        },
        SessionBuilder()
        .prompt("Invoice totals are off by a cent; fix the rounding in totals and add a test")
        .edit("app/invoices/totals.py")
        .bash("pytest tests/invoices", ok=False, output="1 failed")
        .edit("app/invoices/totals.py")
        .write("tests/invoices/test_totals.py")
        .bash("pytest tests/invoices", ok=True, output="8 passed"),
        [],
    )
    write(
        "claimed-command",
        {
            "number": 43,
            "title": "Add CSV export to reports",
            "body": "CSV export for reports. Ran `npm run lint` and `npm test`.",
            "checks": [],
            "files": [{"path": "web/reports/export.ts", "additions": 64, "deletions": 0}],
        },
        SessionBuilder()
        .prompt("Add CSV export to the reports page")
        .write("web/reports/export.ts")
        .bash("npm test", ok=True, output="Tests: 31 passed"),
        [{"sender": "dana", "text": "1: I ran lint in my editor, it was clean."}],
    )
    write(
        "no-trail",
        {
            "number": 44,
            "title": "Bump checkout timeout",
            "body": "Raises the checkout timeout to 30 s.",
            "checks": [{"name": "ci / test", "conclusion": "failure"}],
            "files": [{"path": "app/checkout/config.py", "additions": 1, "deletions": 1}],
        },
        None,
        [{"sender": "dana", "text": "1: The failure is the flaky payments test, unrelated."}],
    )


if __name__ == "__main__":
    main()
