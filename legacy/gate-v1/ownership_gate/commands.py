"""Recognises verification commands (tests, lint, type checks, builds) in shell lines.

Only these commands matter to the gate: a failed `grep` is normal, a failed test run
that was never rerun is a gap.
"""

from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass, field
from enum import StrEnum


class CheckKind(StrEnum):
    TEST = "test"
    LINT = "lint"
    TYPECHECK = "typecheck"
    BUILD = "build"


@dataclass(frozen=True)
class Check:
    """One verification command. `exit_is_own` is False when the shell line's exit code
    may come from a later command (a pipe, `;`, `||`), so success must be read from output."""

    tool: str
    kind: CheckKind
    targets: tuple[str, ...]
    workdir: str = ""
    filters: tuple[str, ...] = ()
    exit_is_own: bool = field(default=True, compare=False)


SINGLE_TOOLS: dict[str, CheckKind] = {
    "pytest": CheckKind.TEST,
    "py.test": CheckKind.TEST,
    "unittest": CheckKind.TEST,
    "tox": CheckKind.TEST,
    "nox": CheckKind.TEST,
    "jest": CheckKind.TEST,
    "vitest": CheckKind.TEST,
    "mocha": CheckKind.TEST,
    "rspec": CheckKind.TEST,
    "phpunit": CheckKind.TEST,
    "playwright": CheckKind.TEST,
    "eslint": CheckKind.LINT,
    "flake8": CheckKind.LINT,
    "pylint": CheckKind.LINT,
    "rubocop": CheckKind.LINT,
    "golangci-lint": CheckKind.LINT,
    "biome": CheckKind.LINT,
    "mypy": CheckKind.TYPECHECK,
    "pyright": CheckKind.TYPECHECK,
    "tsc": CheckKind.TYPECHECK,
}
# Tools whose second word names the check, e.g. `go test`, `cargo build`.
SUBCOMMAND_TOOLS: dict[str, dict[str, CheckKind]] = {
    "ruff": {"check": CheckKind.LINT},
    "go": {"test": CheckKind.TEST, "vet": CheckKind.LINT, "build": CheckKind.BUILD},
    "cargo": {
        "test": CheckKind.TEST,
        "clippy": CheckKind.LINT,
        "build": CheckKind.BUILD,
        "check": CheckKind.TYPECHECK,
    },
    "dotnet": {"test": CheckKind.TEST, "build": CheckKind.BUILD},
    "mvn": {"test": CheckKind.TEST, "verify": CheckKind.TEST, "package": CheckKind.BUILD},
    "gradle": {"test": CheckKind.TEST, "build": CheckKind.BUILD, "check": CheckKind.TEST},
    "./gradlew": {"test": CheckKind.TEST, "build": CheckKind.BUILD, "check": CheckKind.TEST},
    "rails": {"test": CheckKind.TEST},
    "bin/rails": {"test": CheckKind.TEST},
    "make": {
        "test": CheckKind.TEST,
        "check": CheckKind.TEST,
        "lint": CheckKind.LINT,
        "build": CheckKind.BUILD,
    },
    "bun": {"test": CheckKind.TEST},
}
PACKAGE_MANAGERS = frozenset({"npm", "yarn", "pnpm", "bun"})
WRAPPERS: tuple[tuple[str, ...], ...] = (
    ("uv", "run"),
    ("poetry", "run"),
    ("pipenv", "run"),
    ("pdm", "run"),
    ("hatch", "run"),
    ("bundle", "exec"),
    ("pnpm", "exec"),
    ("npm", "exec"),
    ("yarn", "exec"),
    ("python", "-m"),
    ("py", "-m"),
    ("npx",),
    ("bunx",),
    ("sudo",),
    ("env",),
)
# Options of wrappers (`uv run --with x`, `timeout -s KILL 60`) that take a value.
WRAPPER_VALUE_OPTIONS = frozenset(
    {
        "--with",
        "--python",
        "-p",
        "--project",
        "--directory",
        "--extra",
        "--group",
        "--env-file",
        "--package",
        "-s",
        "--signal",
        "-k",
        "--kill-after",
    }
)
# Options of test and lint tools that take a value, so the value is not a target.
VALUE_OPTIONS = frozenset(
    {
        "-k",
        "-m",
        "-n",
        "-p",
        "-c",
        "-o",
        "-W",
        "-t",
        "-g",
        "-j",
        "--cov",
        "--ignore",
        "--deselect",
        "--rootdir",
        "--maxfail",
        "--tb",
        "--junitxml",
        "--testNamePattern",
        "--config",
        "--workers",
        "--jobs",
        "--reporter",
        "--timeout",
        "--durations",
        "--select",
        "--extend-select",
        "--target",
        "--features",
        "--package",
        "--grep",
        "--shard",
    }
)
# Options that narrow a run to part of its targets.
FILTER_OPTIONS = frozenset(
    {
        "-k",
        "-m",
        "-t",
        "--testNamePattern",
        "--deselect",
        "--lf",
        "--last-failed",
        "-g",
        "--grep",
        "--run",
        "--shard",
        "--onlyChanged",
        "-o",
    }
)
FLAG_ONLY_FILTERS = frozenset({"--lf", "--last-failed", "--onlyChanged"})
PYTHON = re.compile(r"^python\d*(?:\.\d+)?$")
EXECUTABLE_SUFFIXES = (".exe", ".cmd", ".bat")
SCRIPT_WORD = re.compile(r"[:\-_.]")
SCRIPT_KINDS = {
    "test": CheckKind.TEST,
    "tests": CheckKind.TEST,
    "spec": CheckKind.TEST,
    "e2e": CheckKind.TEST,
    "lint": CheckKind.LINT,
    "typecheck": CheckKind.TYPECHECK,
    "types": CheckKind.TYPECHECK,
    "tsc": CheckKind.TYPECHECK,
    "build": CheckKind.BUILD,
}
SECRET_ASSIGNMENT = re.compile(
    r"\b([A-Za-z_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASS|AUTH|CREDENTIALS?)[A-Za-z0-9_]*)=\S+",
    re.IGNORECASE,
)
TOKEN_LIKE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}|[A-Za-z0-9+/_-]{40,})"
)
MAX_DISPLAY = 120
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEPARATORS = frozenset({"&&", "||", ";", "|", "&", "|&", ";;", "(", ")"})
REDIRECT_CHARS = frozenset("<>&")
HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?")


def classify(command: str, cwd: str = "") -> Check | None:
    """Return the first verification check in a shell line, or None."""
    checks = classify_all(command, cwd)
    return checks[0] if checks else None


def classify_all(command: str, cwd: str = "") -> list[Check]:
    """Every verification check in a shell line, in order. Heredoc bodies are skipped.

    `cwd` is the shell's directory before the line runs, relative to the session start.
    """
    segments, separators = _segments(_strip_heredocs(command))
    checks: list[Check] = []
    workdir = cwd
    for i, words in enumerate(segments):
        if words[:1] == ["cd"] and len(words) == 2:
            workdir = join_dir(workdir, words[1])
            continue
        found = _match(_unwrap(words))
        if found is None:
            continue
        tool, kind, args = found
        targets, filters = _targets_and_filters(args)
        own = all(sep == "&&" for sep in separators[i:])
        checks.append(Check(tool, kind, targets, workdir, filters, exit_is_own=own))
    return checks


def display_command(command: str) -> str:
    """One line of a command, safe to post in chat: secrets masked, heredocs dropped."""
    lines = [line.strip() for line in _strip_heredocs(command).splitlines() if line.strip()]
    text = lines[0] if lines else ""
    text = SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}=***", text)
    text = TOKEN_LIKE.sub("***", text)
    if len(lines) > 1 or len(text) > MAX_DISPLAY:
        text = text[:MAX_DISPLAY].rstrip() + " ..."
    return text.replace("`", "'")


def cwd_after(command: str, cwd: str) -> str:
    """The shell's directory after a line runs: Claude Code keeps it between commands."""
    segments, separators = _segments(_strip_heredocs(command))
    for i, words in enumerate(segments):
        in_subshell = "(" in separators[:i] and ")" not in separators[:i]
        if words[:1] == ["cd"] and len(words) == 2 and not in_subshell:
            cwd = join_dir(cwd, words[1])
    return cwd


def join_dir(cwd: str, target: str) -> str:
    target = _normalise_path(target)
    if target.startswith("/") or re.match(r"^[A-Za-z]:", target):
        return posixpath.normpath(target)
    joined = posixpath.normpath(posixpath.join(cwd or ".", target))
    return "" if joined == "." else joined


def covers(later: Check | None, earlier: Check | None) -> bool:
    """True when `later` re-checks everything `earlier` checked."""
    if later is None or earlier is None:
        return False
    if (later.tool, later.workdir) != (earlier.tool, earlier.workdir):
        return False
    if not set(later.filters) <= set(earlier.filters):
        return False
    if not later.targets:
        return True
    if not earlier.targets:
        return any(_within(".", scope) for scope in later.targets)
    return all(any(_within(e, scope) for scope in later.targets) for e in earlier.targets)


def _within(target: str, scope: str) -> bool:
    if scope in (".", "./..."):
        return True
    return target == scope or target.startswith((scope + "/", scope + "::"))


def _strip_heredocs(command: str) -> str:
    kept: list[str] = []
    delimiter = ""
    for line in command.splitlines():
        if delimiter:
            if line.strip() == delimiter:
                delimiter = ""
            continue
        kept.append(line)
        found = HEREDOC.search(line)
        if found:
            delimiter = found.group(1)
    return "\n".join(kept)


def _segments(command: str) -> tuple[list[list[str]], list[str]]:
    """Split into simple commands and the separators between them, respecting quotes."""
    segments: list[list[str]] = [[]]
    separators: list[str] = []
    for line_number, line in enumerate(command.splitlines()):
        if line_number:
            segments.append([])
            separators.append(";")
        tokens = _tokens(line)
        skip_next = False
        for token in tokens:
            if skip_next:
                skip_next = False
            elif token in SEPARATORS:
                segments.append([])
                separators.append(token)
            elif set(token) <= REDIRECT_CHARS:
                skip_next = True
                if segments[-1] and segments[-1][-1].isdigit():
                    segments[-1].pop()
            else:
                segments[-1].append(token)
    return [_drop_env(s) for s in segments], separators


def _tokens(line: str) -> list[str]:
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return line.split()


def _drop_env(words: list[str]) -> list[str]:
    while words and ENV_ASSIGNMENT.match(words[0]):
        words = words[1:]
    return words


def _unwrap(words: list[str]) -> list[str]:
    words = [_tool_name(words[0]), *words[1:]] if words else words
    changed = True
    while changed:
        changed = False
        if words[:1] == ["timeout"]:
            words = _skip_options(words[1:])[1:]
            changed = True
        for wrapper in WRAPPERS:
            if tuple(words[: len(wrapper)]) == wrapper and len(words) > len(wrapper):
                words = _drop_env(_skip_options(words[len(wrapper) :]))
                changed = True
                break
        if words and changed:
            words = [_tool_name(words[0]), *words[1:]]
    return words


def _tool_name(word: str) -> str:
    """`.venv/bin/pytest`, `pytest.exe` and `python3.12` name the same tools as their bases."""
    if "/" in word and word not in SUBCOMMAND_TOOLS:
        word = word.rsplit("/", 1)[1]
    lowered = word.lower()
    for suffix in EXECUTABLE_SUFFIXES:
        if lowered.endswith(suffix):
            word = word[: -len(suffix)]
    return "python" if PYTHON.match(word) else word


def _skip_options(words: list[str]) -> list[str]:
    while words and words[0].startswith("-"):
        takes_value = words[0] in WRAPPER_VALUE_OPTIONS and "=" not in words[0]
        words = words[2:] if takes_value else words[1:]
    return words


def _targets_and_filters(args: list[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    targets: list[str] = []
    filters: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        name, _, inline = arg.partition("=")
        if arg in FLAG_ONLY_FILTERS:
            filters.append(arg)
        elif arg.startswith("-") and name in VALUE_OPTIONS:
            value = inline if inline else (args[i + 1] if i + 1 < len(args) else "")
            if name in FILTER_OPTIONS:
                filters.append(f"{name}={value}")
            i += 0 if inline else 1
        elif not arg.startswith("-"):
            targets.append(_normalise_path(arg))
        i += 1
    return tuple(targets), tuple(filters)


def _match(words: list[str]) -> tuple[str, CheckKind, list[str]] | None:
    if not words:
        return None
    head = words[0]
    if head in SINGLE_TOOLS:
        return head.replace("py.test", "pytest"), SINGLE_TOOLS[head], words[1:]
    if head in PACKAGE_MANAGERS:
        return _match_script(head, words[1:])
    if words[:2] == ["ruff", "format"] and "--check" in words:
        return "ruff format", CheckKind.LINT, words[2:]
    sub = SUBCOMMAND_TOOLS.get(head, {})
    if len(words) > 1 and words[1] in sub:
        return f"{head.removeprefix('bin/')} {words[1]}", sub[words[1]], words[2:]
    return None


def _match_script(manager: str, rest: list[str]) -> tuple[str, CheckKind, list[str]] | None:
    if rest[:1] in (["test"], ["t"]):
        return f"{manager} test", CheckKind.TEST, rest[1:]
    if rest[:1] == ["run"]:
        rest = rest[1:]
        prefix = f"{manager} run"
    else:
        prefix = manager
    if not rest:
        return None
    kind = _script_kind(rest[0])
    return (f"{prefix} {rest[0]}", kind, rest[1:]) if kind else None


def _script_kind(script: str) -> CheckKind | None:
    words = [w.lower() for w in SCRIPT_WORD.split(script)]
    if "type" in words and "check" in words:
        return CheckKind.TYPECHECK
    return next((SCRIPT_KINDS[w] for w in words if w in SCRIPT_KINDS), None)


def _normalise_path(arg: str) -> str:
    path = arg.replace("\\", "/")
    while path.startswith("./") and path != "./...":
        path = path[2:]
    return path.rstrip("/") or path
