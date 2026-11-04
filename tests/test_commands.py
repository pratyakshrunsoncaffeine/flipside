import pytest

from ownership_gate.commands import CheckKind, classify, covers


@pytest.mark.parametrize(
    ("command", "tool", "kind", "targets"),
    [
        ("pytest tests/test_billing.py", "pytest", CheckKind.TEST, ("tests/test_billing.py",)),
        ("python -m pytest -q", "pytest", CheckKind.TEST, ()),
        ("uv run pytest tests/", "pytest", CheckKind.TEST, ("tests",)),
        ("cd api && npm test", "npm test", CheckKind.TEST, ()),
        ("npm run build", "npm run build", CheckKind.BUILD, ()),
        ("pnpm lint", "pnpm lint", CheckKind.LINT, ()),
        ("go test ./...", "go test", CheckKind.TEST, ("./...",)),
        ("cargo test", "cargo test", CheckKind.TEST, ()),
        ("bundle exec rspec spec/models", "rspec", CheckKind.TEST, ("spec/models",)),
        (
            "bin/rails test test/models/user_test.rb",
            "rails test",
            CheckKind.TEST,
            ("test/models/user_test.rb",),
        ),
        ("ruff check .", "ruff check", CheckKind.LINT, (".",)),
        ("npx tsc --noEmit", "tsc", CheckKind.TYPECHECK, ()),
        ("CI=1 npx jest src/a.test.ts", "jest", CheckKind.TEST, ("src/a.test.ts",)),
    ],
)
def test_classifies_verification_commands(command, tool, kind, targets):
    check = classify(command)

    assert check is not None
    assert (check.tool, check.kind, check.targets) == (tool, kind, targets)


@pytest.mark.parametrize("command", ["ls -la", "grep -rn foo .", "git status", "cat README.md", ""])
def test_ignores_non_verification_commands(command):
    assert classify(command) is None


def test_records_working_directory_from_cd():
    assert classify("cd web && npm test").workdir == "web"
    assert classify("npm test").workdir == ""


def test_finds_check_after_a_pipe_or_chain():
    check = classify("git stash && pytest tests/a.py | tail -5")

    assert check is not None
    assert check.targets == ("tests/a.py",)


def test_whole_suite_covers_a_single_file():
    assert covers(classify("pytest"), classify("pytest tests/test_a.py"))


def test_directory_covers_file_and_node_id():
    assert covers(classify("pytest tests/"), classify("pytest tests/test_a.py::test_x"))
    assert covers(classify("pytest tests/test_a.py"), classify("pytest tests/test_a.py::test_x"))


def test_narrower_run_does_not_cover_wider_run():
    assert not covers(classify("pytest tests/test_a.py"), classify("pytest"))


def test_different_tool_or_directory_does_not_cover():
    assert not covers(classify("npm test"), classify("pytest"))
    assert not covers(classify("cd web && npm test"), classify("cd api && npm test"))


def test_sibling_path_with_shared_prefix_does_not_cover():
    assert not covers(classify("pytest tests/api"), classify("pytest tests/api_v2/test_a.py"))


def test_redirects_are_not_targets():
    assert classify("pytest -q 2>&1").targets == ()
    assert classify("pytest tests/a.py > out.txt").targets == ("tests/a.py",)
    assert classify("pytest tests/a.py 2>/dev/null").targets == ("tests/a.py",)


def test_ruff_format_counts_only_with_check_flag():
    assert classify("ruff format .") is None
    assert classify("ruff format --check .").tool == "ruff format"


def test_exit_code_ownership_follows_the_separators():
    from ownership_gate.commands import classify_all

    lint, test = classify_all("ruff check . && pytest | tail -3")

    assert (lint.tool, test.tool) == ("ruff check", "pytest")
    assert not lint.exit_is_own
    assert not test.exit_is_own
    assert classify_all("ruff check . && pytest")[0].exit_is_own


def test_heredoc_bodies_are_not_commands():
    command = "python - <<'EOF'\nimport os\nos.system('pytest')\nruff check .\nEOF\nls"

    assert classify(command) is None


def test_pipes_inside_quotes_do_not_split():
    assert classify("grep -E 'a|pytest' log.txt") is None
    assert classify('git commit -m "fix: make pytest pass"') is None


@pytest.mark.parametrize(
    "command",
    [
        ".venv/bin/pytest tests/a.py",
        "pytest.exe tests/a.py",
        "python3.12 -m pytest tests/a.py",
        "uv run --with pytest-xdist pytest tests/a.py",
        "env CI=1 pytest tests/a.py",
        "timeout -s KILL 60 pytest tests/a.py",
        "pytest -s tests/a.py",
    ],
)
def test_common_spellings_of_one_pytest_run(command):
    check = classify(command)

    assert (check.tool, check.targets) == ("pytest", ("tests/a.py",))


def test_option_values_are_filters_not_targets():
    check = classify("pytest tests/test_a.py -k refund -n 4")

    assert check.targets == ("tests/test_a.py",)
    assert check.filters == ("-k=refund",)


def test_filtered_run_does_not_cover_a_full_run_but_the_reverse_holds():
    full, filtered = classify("pytest tests/a.py"), classify("pytest tests/a.py -k refund")

    assert covers(full, filtered)
    assert not covers(filtered, full)
    assert not covers(classify("pytest --lf"), classify("pytest"))


def test_script_names_match_whole_words():
    assert classify("npm run latest") is None
    assert classify("npm run test:unit").kind is CheckKind.TEST
    assert classify("pnpm type-check").kind is CheckKind.TYPECHECK


def test_cd_joins_the_previous_directory():
    from ownership_gate.commands import cwd_after

    assert classify("cd web && npm test", cwd="apps").workdir == "apps/web"
    assert cwd_after("cd backend && pytest", "") == "backend"
    assert cwd_after("cd ..", "backend") == ""
    assert cwd_after("(cd web && npm test)", "") == ""


def test_display_command_masks_secrets_and_drops_heredocs():
    from ownership_gate.commands import display_command

    shown = display_command("OPENAI_API_KEY=sk-abcdefghijklmnopqrstu pytest <<'EOF'\nsecret\nEOF")

    assert shown == "OPENAI_API_KEY=*** pytest <<'EOF'"
    assert "ghp_" not in display_command("curl -H ghp_abcdefghijklmnopqrstuvwxyz0123 x")
