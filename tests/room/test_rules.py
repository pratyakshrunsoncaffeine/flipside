"""Gap, selection and contradiction rules: one firing and one non-firing case each."""

from typing import Any

from flipside.room.rules import (
    MAX_LINES,
    CheckRun,
    Gap,
    PRData,
    asked,
    contradictions,
    gaps,
    is_lockfile,
    select,
)

F, G = "auth/session.py", "reports/export.py"


def e(
    i: int,
    step: int,
    role: str = "assistant",
    tools: list[str] | None = None,
    files: list[str] | None = None,
    mentions: list[str] | None = None,
    cmd: str | None = None,
    ok: bool | None = None,
    session: int = 0,
    chunk: int = 0,
) -> dict[str, Any]:
    return {
        "i": i,
        "v": 1,
        "session": session,
        "step": step,
        "chunk": chunk,
        "role": role,
        "tools": tools or [],
        "files": files or [],
        "mentions": mentions or [],
        "cmd": cmd,
        "ok": ok,
    }


MANIFEST = [
    e(0, 0, "user"),
    e(1, 1, tools=["Edit"], files=[G]),
    e(2, 2, "tool_result", ["Edit"], [G]),
    e(3, 3, tools=["Bash"], cmd="test"),
    e(4, 4, "tool_result", ["Bash"], cmd="test", ok=False),
    e(5, 5),
    e(6, 6, tools=["Edit"], files=[F]),
    e(7, 6, tools=["Edit"], files=[F], chunk=1),
    e(8, 7, "tool_result", ["Edit"], [F]),
    e(9, 8, tools=["Bash"], cmd="test"),
    e(10, 9, "tool_result", ["Bash"], cmd="test", ok=True),
    e(11, 10),
]


def pr(
    title: str = "Add CSV export",
    body: str = "Adds CSV export to the reports page.",
    files: tuple[str, ...] = (F, G),
    checks: tuple[CheckRun, ...] = (),
    changed_lines: int | None = None,
) -> PRData:
    return PRData(142, title, body, "priya", files, checks, changed_lines)


def kinds(gs: list[Gap]) -> list[tuple[str, str | None]]:
    return [(g.kind, g.file or g.check) for g in gs]


def test_scope_fires_and_not() -> None:
    assert kinds(gaps(pr(), MANIFEST)) == [("SCOPE", F)]
    assert kinds(gaps(pr(body="Adds CSV export; raises the session TTL."), MANIFEST)) == []
    assert kinds(gaps(pr(body=f"Touches {F.upper()} too"), MANIFEST)) == []


def test_ci_fires_and_not() -> None:
    fail = pr(
        body="x session export", checks=(CheckRun("lint", "failure"), CheckRun("test", "success"))
    )
    assert kinds(gaps(fail, MANIFEST)) == [("CI", "lint")]
    ok = pr(body="x session export", checks=(CheckRun("test", "success"), CheckRun("e2e", None)))
    assert gaps(ok, MANIFEST) == []


def test_tests_fires_on_failed_last_run_and_not_on_pass() -> None:
    m = MANIFEST[:5]
    g = gaps(pr(body="session export. Tests pass.", files=(G,)), m)
    assert kinds(g) == [("TESTS", None)]
    assert "step `4`" in g[0].text
    assert gaps(pr(body="session export. Tests pass."), MANIFEST) == []
    # No pass claim: the failed last run is asked as RERUN instead.
    assert kinds(gaps(pr(body="session export. tests are flaky", files=(G,)), m)) == [
        ("RERUN", None)
    ]


def test_tests_fires_when_no_test_ran() -> None:
    m = MANIFEST[:3]
    g = gaps(pr(body="export: tests green", files=(G,)), m)
    assert kinds(g) == [("TESTS", None)] and "No sealed step ran tests" in g[0].text


def test_unsealed_fires_and_not() -> None:
    g = gaps(pr(body="export session", files=(F, G, "README.md")), MANIFEST)
    assert kinds(g) == [("UNSEALED", "README.md")]
    assert gaps(pr(body="export session"), MANIFEST) == []


def test_bash_mention_counts_as_touch() -> None:
    m = [e(0, 0, tools=["Bash"], mentions=[F], cmd="other")]
    assert kinds(gaps(pr(files=(F,)), m)) == [("SCOPE", F)]
    assert select(gaps(pr(files=(F,)), m)[0], m).leaves == (0,)


def test_no_seal_gives_unsealed_only() -> None:
    assert kinds(gaps(pr(), None)) == [("UNSEALED", F), ("UNSEALED", G)]


def test_order_and_cap_at_five() -> None:
    files = tuple(f"x{i}.py" for i in range(7))
    gs = gaps(pr(files=files, checks=(CheckRun("ci", "failure"),)), MANIFEST)
    first, rest = asked(gs)
    assert [g.kind for g in first] == ["CI", "UNSEALED", "UNSEALED", "UNSEALED", "UNSEALED"]
    assert len(rest) == 3


def test_select_scope_edit_step_plus_text_step_before() -> None:
    s = select(Gap("SCOPE", "", file=F), MANIFEST)
    assert s.leaves == (7, 6, 5)
    assert s.anchored == frozenset({6, 7})


def test_select_scope_no_text_step_across_user_boundary() -> None:
    m = [e(0, 0), e(1, 1, "user"), e(2, 2, tools=["Edit"], files=[F])]
    assert select(Gap("SCOPE", "", file=F), m).leaves == (2,)


def test_select_tests_last_call_and_result() -> None:
    assert select(Gap("TESTS", ""), MANIFEST).leaves == (10, 9)
    assert select(Gap("CI", ""), MANIFEST[:5]).leaves == (4, 3)
    assert select(Gap("TESTS", ""), MANIFEST[:3]).leaves == ()


def test_select_unsealed_is_text_only() -> None:
    assert select(Gap("UNSEALED", "", file="README.md"), MANIFEST).leaves == ()


def test_select_cap_eight_most_recent_first() -> None:
    m = [e(i, 0, tools=["Edit"], files=[F], chunk=i) for i in range(12)]
    assert select(Gap("SCOPE", "", file=F), m).leaves == (11, 10, 9, 8, 7, 6, 5, 4)


def leaf(text: str = "", ok: bool | None = None, files: list[str] | None = None) -> dict[str, Any]:
    return {"text": text, "ok": ok, "files": files or [], "mentions": []}


def test_c_tests_fires_and_not() -> None:
    gap = Gap("TESTS", "")
    bad = [{"i": 4, "leaf": leaf("Exit code 1\nFAILED t.py", ok=False)}]
    assert [c.rule for c in contradictions(1, "they passed locally", gap, bad, frozenset())] == [
        "C-TESTS"
    ]
    assert contradictions(1, "the run failed, I fixed it later", gap, bad, frozenset()) == []
    good = [{"i": 10, "leaf": leaf("3 passed", ok=True)}]
    assert contradictions(1, "they pass", gap, good, frozenset()) == []
    assert contradictions(1, None, gap, bad, frozenset()) == []


def test_c_tests_on_error_text() -> None:
    v = [{"i": 1, "leaf": leaf("Error: boom")}]
    assert [c.rule for c in contradictions(2, "green", Gap("CI", ""), v, frozenset())] == [
        "C-TESTS"
    ]


def test_c_file_fires_only_on_anchored_leaf() -> None:
    gap = Gap("SCOPE", "", file=F)
    v = [{"i": 5, "leaf": leaf("context")}, {"i": 6, "leaf": leaf("edit", files=[F])}]
    assert contradictions(1, "why", gap, v, frozenset({6})) == []
    assert [c.rule for c in contradictions(1, "why", gap, v, frozenset({5}))] == ["C-FILE"]


def test_tests_skips_a_test_call_that_never_ran() -> None:
    # C14: a passing run, then a rerun the author rejected (ok null). Not a failure.
    m = [
        *MANIFEST,
        e(12, 11, tools=["Bash"], cmd="test"),
        e(13, 12, "tool_result", ["Bash"], cmd="test"),
    ]
    assert gaps(pr(body="session export. Tests pass."), m) == []
    assert select(Gap("TESTS", ""), m).leaves == (10, 9)


def test_tests_with_only_never_ran_calls_means_no_test_ran() -> None:
    m = [
        *MANIFEST[:3],
        e(3, 3, tools=["Bash"], cmd="test"),
        e(4, 4, "tool_result", ["Bash"], cmd="test"),
    ]
    g = gaps(pr(body="export: tests green", files=(G,)), m)
    assert kinds(g) == [("TESTS", None)] and "No sealed step ran tests" in g[0].text


def test_c_tests_ignores_a_bash_call_that_never_ran() -> None:
    # C14: the author offers a rejected call; "Error:" in its text is not a failed run.
    never = {
        **leaf("<tool_use_error>InputValidationError: command is required</tool_use_error>"),
        "role": "tool_result",
        "tools": ["Bash"],
    }
    v = [{"i": 13, "leaf": never}]
    assert contradictions(1, "tests pass", Gap("TESTS", ""), v, frozenset()) == []


def test_scope_test_file_counts_as_mentioned_when_the_body_says_it_adds_tests() -> None:
    # Found on a real PR: "Adds render_json to report.py ..., with tests." still asked
    # why tests/test_report.py changed.
    t = "tests/test_report.py"
    m = [e(0, 0, "user"), e(1, 1, tools=["Edit"], files=["report.py", t])]
    for body in (
        "Adds render_json to report.py, with tests.",
        "Adds tests for report.py.",
        "report.py: new JSON output; added unit tests.",
    ):
        assert gaps(pr(body=body, files=("report.py", t)), m) == [], body
    # "Tests pass" is a claim about a run, not a change to tests: the question stays.
    g = gaps(pr(body="Adds JSON to report.py. Tests pass.", files=("report.py", t)), m)
    assert kinds(g) == [("TESTS", None), ("SCOPE", t)]
    # The test's subject must be mentioned too.
    assert kinds(gaps(pr(body="Adds render_json, with tests.", files=(t,)), m)) == [("SCOPE", t)]


LINT_RUN = [
    e(12, 11, tools=["Bash"], cmd="lint"),
    e(13, 12, "tool_result", ["Bash"], cmd="lint", ok=False),
]


def test_lint_claim_fires_when_no_lint_ran_or_the_last_failed() -> None:
    body = "session export. Ruff is clean."
    g = gaps(pr(body=body), MANIFEST)
    assert kinds(g) == [("LINT", None)] and "No sealed step ran lint" in g[0].text
    g = gaps(pr(body=body), [*MANIFEST, *LINT_RUN])
    assert kinds(g) == [("LINT", None)] and "step `12`" in g[0].text
    passed = [LINT_RUN[0], {**LINT_RUN[1], "ok": True}]
    assert gaps(pr(body=body), [*MANIFEST, *passed]) == []


def test_lint_and_build_need_a_pass_claim() -> None:
    for body in (
        "session export. Fixed the lint warnings.",
        "session export. A build step that passes flags to the linter.",
        "session export. Build passes: see CI.",
    ):
        got = kinds(gaps(pr(body=body), MANIFEST))
        assert got == ([("BUILD", None)] if body.startswith("session export. Build") else []), body


def test_build_claim_fires_and_not() -> None:
    body = "session export. The build succeeded."
    assert kinds(gaps(pr(body=body), MANIFEST)) == [("BUILD", None)]
    ran = [
        e(12, 11, tools=["Bash"], cmd="build"),
        e(13, 12, "tool_result", ["Bash"], cmd="build", ok=True),
    ]
    assert gaps(pr(body=body), [*MANIFEST, *ran]) == []


def test_lint_claim_skips_a_call_that_never_ran() -> None:
    never = [LINT_RUN[0], {**LINT_RUN[1], "ok": None}]
    g = gaps(pr(body="session export. mypy passes."), [*MANIFEST, *never])
    assert kinds(g) == [("LINT", None)] and "No sealed step ran lint" in g[0].text


def test_rerun_fires_without_a_claim_and_not_after_a_passing_rerun() -> None:
    g = gaps(pr(body="session export", files=(G,)), MANIFEST[:5])
    assert kinds(g) == [("RERUN", None)] and g[0].step == (0, 4)
    assert gaps(pr(body="session export"), MANIFEST) == []


def test_size_fires_over_the_limit_and_not_at_it() -> None:
    g = gaps(pr(body="session export", changed_lines=MAX_LINES + 1), MANIFEST)
    assert kinds(g) == [("SIZE", None)] and f"{MAX_LINES + 1} lines" in g[0].text
    assert gaps(pr(body="session export", changed_lines=MAX_LINES), MANIFEST) == []
    assert gaps(pr(body="session export", changed_lines=None), MANIFEST) == []


def test_new_rules_come_after_the_build_md_rules() -> None:
    body = "x session export. Lint passes."
    g = gaps(pr(body=body, files=(F, G, "README.md"), changed_lines=900), MANIFEST)
    assert [k for k, _ in kinds(g)] == ["UNSEALED", "LINT", "SIZE"]


def test_is_lockfile() -> None:
    assert is_lockfile("web/package-lock.json") and is_lockfile("uv.lock")
    assert not is_lockfile("src/lock.py")


def test_select_lint_and_rerun() -> None:
    m = [*MANIFEST, *LINT_RUN]
    assert select(Gap("LINT", ""), m).leaves == (13, 12)
    assert select(Gap("BUILD", ""), m).leaves == ()
    assert select(Gap("RERUN", ""), MANIFEST[:5]).leaves == (4, 3)
    assert select(Gap("SIZE", ""), m).leaves == ()
