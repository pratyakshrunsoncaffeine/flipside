"""Claude Code session JSONL to sealed steps (docs/seal/SPEC.md, Steps to Chunks).

The parse is a pure function of the sealed bytes, the repo root, the PR's
changed-file list and any stored tool-results files, so prove can rebuild
exactly the leaves seal hashed.
"""

import base64
import binascii
import hashlib
import json
import os
import posixpath
import re
import shlex
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from flipside.seal.canon import CanonError, canon_text

CHUNK = 300
EXTERNAL = "<external>"
PATH_KEYS = ("file_path", "notebook_path", "path")

# (class, command words). Longest match wins, so "make test" beats "make".
CMD_TABLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("test", ("pytest",)),
    ("test", ("unittest",)),
    ("test", ("go", "test")),
    ("test", ("cargo", "test")),
    ("test", ("make", "test")),
    ("test", ("vitest",)),
    ("test", ("jest",)),
    ("lint", ("ruff",)),
    ("lint", ("mypy",)),
    ("lint", ("eslint",)),
    ("lint", ("tsc", "--noEmit")),
    ("lint", ("flake8",)),
    ("lint", ("black", "--check")),
    ("lint", ("make", "lint")),
    ("build", ("cargo", "build")),
    ("build", ("go", "build")),
    ("build", ("make",)),
    ("build", ("docker", "build")),
)
CMD_PRIORITY = {"test": 3, "lint": 2, "build": 1, "other": 0}

_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PYTHON = re.compile(r"^python(3(\.\d+)?)?$")
_POINTER = re.compile(r"Full output saved to: (\S+)")


class SessionError(ValueError):
    """The session bytes cannot be parsed."""


@dataclass
class Step:
    """One sealed step: a message, with the public metadata of SPEC Step metadata."""

    session: int
    step: int
    role: str
    tools: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    cmd: str | None = None
    ok: bool | None = None
    text: str = ""
    parts: list[str] = field(default_factory=list, repr=False)


@dataclass(frozen=True)
class _Call:
    name: str
    files: list[str]
    mentions: list[str]
    cmd: str | None


def sealed_prefix(data: bytes) -> bytes:
    """The bytes up to and including the last newline: sealing cuts at the last full line."""
    cut = data.rfind(b"\n")
    return data[: cut + 1] if cut >= 0 else b""


def chunks(text: str) -> list[str]:
    """Normalise (CRLF to LF, NFC) and split into chunks of at most 300 code points.

    Cut after the last space or newline inside the window; with none, cut at 300.
    An empty text gives one empty chunk.
    """
    t = unicodedata.normalize("NFC", text.replace("\r\n", "\n"))
    out: list[str] = []
    while len(t) > CHUNK:
        window = t[:CHUNK]
        cut = max(window.rfind(" "), window.rfind("\n"))
        cut = cut + 1 if cut >= 0 else CHUNK
        out.append(t[:cut])
        t = t[cut:]
    out.append(t)
    return out


# Launcher flags that take a separate value ("--project x"); "--project=x" needs no entry.
UV_VALUE_FLAGS = frozenset(
    {
        "--with",
        "--with-editable",
        "--with-requirements",
        "--project",
        "--directory",
        "--python",
        "-p",
        "--package",
        "--extra",
        "--group",
        "--only-group",
        "--no-group",
        "--env-file",
        "--index",
        "--index-url",
        "--default-index",
        "--extra-index-url",
        "--find-links",
        "-f",
        "--config-file",
        "--cache-dir",
        "--python-platform",
        "--color",
        "-C",
        "--config-setting",
    }
)
NPX_VALUE_FLAGS = frozenset({"--package", "-p", "--call", "-c"})
PYTHON_VALUE_FLAGS = frozenset({"-X", "-W", "--check-hash-based-pycs"})
# C15: wrappers that run the next word as the command, with their value-taking flags.
WRAPPERS: dict[str, frozenset[str]] = {
    "env": frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "time": frozenset({"-f", "--format", "-o", "--output"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "exec": frozenset({"-a"}),
    "command": frozenset(),
}
PACKAGE_MANAGERS = frozenset({"npm", "pnpm", "yarn", "bun"})
SCRIPT_CLASSES = ("test", "lint", "build")
_SEPARATOR = re.compile(r"^[&|;()]+$")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _strip_flags(words: list[str], value_flags: frozenset[str], stop: str = "") -> list[str]:
    """Drop leading launcher flags, and the value after a flag that takes one.

    Stops at ``stop`` (kept), so ``python -u -m pytest`` leaves ``-m pytest``.
    """
    while words and words[0].startswith("-") and words[0] != stop:
        words = words[2:] if words[0] in value_flags else words[1:]
    return words


# C14: error results for Bash calls that never ran. The user rejected or interrupted
# the call, a permission rule or hook denied it, or its input was invalid.
NEVER_RAN_PREFIXES = (
    "The user doesn't want to proceed",
    "Permission to use",
    "Permission for this",
    "[Request interrupted",
    "<tool_use_error>",
    "PreToolUse:",
)


def _first_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                t = item.get("text")
                return t if isinstance(t, str) else ""
    return ""


def _bash_ok(b: dict[str, Any]) -> bool | None:
    """``ok`` for a Bash ``tool_result``: true, false, or null when the call never ran."""
    if b.get("is_error") is not True:
        return True
    if _first_text(b.get("content")).lstrip().startswith(NEVER_RAN_PREFIXES):
        return None
    return False


def classify_cmd(command: str) -> str:
    """Command class (test, lint, build, other) of a Bash command (SPEC cmd table, C15).

    Each shell segment (split at unquoted ``&&``, ``||``, ``;``, ``|``, ``&``,
    parentheses and newlines, heredoc bodies dropped) is classified on its first
    command word after stripping env assignments, wrappers (``env``, ``timeout``,
    ``time``, ``nice``, ``exec``, ``command``), ``uv run``, ``npx`` and ``python -m``.
    The command's class is the highest of its segments.
    """
    best = "other"
    for words in _segments(command):
        cls = _classify_words(words)
        if CMD_PRIORITY[cls] > CMD_PRIORITY[best]:
            best = cls
    return best


def _strip_heredocs(command: str) -> str:
    out: list[str] = []
    end: str | None = None
    for line in command.split("\n"):
        if end is not None:
            if line.strip() == end:
                end = None
            continue
        out.append(line)
        if (m := _HEREDOC.search(line)) is not None:
            end = m.group(2)
    return "\n".join(out)


def _segments(command: str) -> list[list[str]]:
    text = _strip_heredocs(command).replace("\n", " ; ")
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        return [command.split()]
    segments: list[list[str]] = [[]]
    for t in tokens:
        if _SEPARATOR.match(t):
            segments.append([])
        else:
            segments[-1].append(t)
    return [w for w in segments if w]


def _classify_words(words: list[str]) -> str:
    while True:
        before = list(words)
        while words and _ENV.match(words[0]):
            words = words[1:]
        head = posixpath.basename(words[0]) if words else ""
        if head == "command" and words[1:2] and words[1] in ("-v", "-V"):
            return "other"
        if head in WRAPPERS:
            words = _strip_flags(words[1:], WRAPPERS[head])
            if head == "timeout" and words:
                words = words[1:]
        elif words[:2] == ["uv", "run"]:
            words = _strip_flags(words[2:], UV_VALUE_FLAGS)
        elif words[:1] == ["npx"]:
            words = _strip_flags(words[1:], NPX_VALUE_FLAGS)
        elif words and _PYTHON.match(words[0]):
            rest = _strip_flags(words[1:], PYTHON_VALUE_FLAGS, stop="-m")
            if rest[:1] == ["-m"]:
                words = rest[1:]
        if words == before:
            break
    if not words:
        return "other"
    words = [posixpath.basename(words[0]), *words[1:]]
    if words[0] in PACKAGE_MANAGERS:
        return _script_cmd(words[0], words[1:])
    best, best_len = "other", 0
    for cls, pattern in CMD_TABLE:
        if tuple(words[: len(pattern)]) == pattern and len(pattern) > best_len:
            best, best_len = cls, len(pattern)
    return best


def _script_cmd(manager: str, args: list[str]) -> str:
    """``npm test``, ``npm run test:unit``, ``pnpm lint``, ``yarn build``, ``bun test``."""
    if args[:1] in (["run"], ["run-script"]):
        script = args[1] if len(args) > 1 else ""
    elif manager == "npm":
        script = "test" if args[:1] in (["test"], ["t"]) else ""
    else:
        script = args[0] if args else ""
    for cls in SCRIPT_CLASSES:
        if script == cls or script.startswith(cls + ":"):
            return cls
    return "other"


def _rel_path(p: str, cwd: str, repo_root: str) -> str:
    base = cwd if os.path.isabs(cwd) else os.path.join(repo_root, cwd)
    absolute = os.path.normpath(os.path.join(base, p))
    root = os.path.normpath(repo_root)
    for a, r in ((absolute, root), (os.path.realpath(absolute), os.path.realpath(root))):
        if a == r or a.startswith(r.rstrip(os.sep) + os.sep):
            return os.path.relpath(a, r).replace(os.sep, "/")
    return EXTERNAL


def _image(block: dict[str, Any]) -> str:
    src = block.get("source") or {}
    data: bytes
    if isinstance(src, dict) and src.get("type") == "base64" and isinstance(src.get("data"), str):
        try:
            data = base64.b64decode(src["data"], validate=False)
        except (binascii.Error, ValueError):
            data = src["data"].encode("utf-8")
    else:
        data = canon_text(src).encode("utf-8")
    return f"[image sha256:{hashlib.sha256(data).hexdigest()}]"


def _str(x: object) -> str:
    return x if isinstance(x, str) else ""


def _dict(x: object) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _add_unique(dst: list[str], items: Sequence[str]) -> None:
    for x in items:
        if x not in dst:
            dst.append(x)


class _Parser:
    def __init__(
        self,
        session: int,
        repo_root: str,
        changed_files: Sequence[str],
        main: bool,
        tool_results_dir: str | None,
        aux_reads: dict[str, bytes] | None,
    ) -> None:
        self.session = session
        self.repo_root = repo_root
        self.changed = sorted(set(changed_files))
        self.main = main
        self.tr_dir = os.path.normpath(tool_results_dir) if tool_results_dir else None
        self.aux_reads = aux_reads
        self.steps: list[Step] = []
        self.by_msg: dict[str, Step] = {}
        self.calls: dict[str, _Call] = {}

    def new(self, role: str) -> Step:
        s = Step(session=self.session, step=len(self.steps), role=role)
        self.steps.append(s)
        return s

    def line(self, d: dict[str, Any]) -> None:
        typ = d.get("type")
        if typ not in ("user", "assistant") or d.get("isMeta") is True:
            return
        if self.main and d.get("isSidechain") is True:
            return
        msg = d.get("message")
        if not isinstance(msg, dict):
            return
        cwd = _str(d.get("cwd"))
        if typ == "assistant":
            self.assistant(msg, cwd)
        else:
            self.user(msg)

    def assistant(self, msg: dict[str, Any], cwd: str) -> None:
        mid = msg.get("id")
        if isinstance(mid, str) and mid in self.by_msg:
            step = self.by_msg[mid]
        else:
            step = self.new("assistant")
            if isinstance(mid, str):
                self.by_msg[mid] = step
        content = msg.get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
        if not isinstance(blocks, list):
            return
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and isinstance(b.get("text"), str):
                step.parts.append(b["text"])
            elif b.get("type") == "tool_use":
                self.tool_use(step, b, cwd)

    def tool_use(self, step: Step, b: dict[str, Any], cwd: str) -> None:
        name = _str(b.get("name"))
        inp = _dict(b.get("input"))
        try:
            rendered = canon_text(inp)
        except CanonError as e:
            raise SessionError(f"tool input of {name} cannot be rendered: {e}") from e
        step.parts.append(f"[tool {name}] {rendered}")
        step.tools.append(name)
        files = [
            _rel_path(inp[k], cwd, self.repo_root) for k in PATH_KEYS if isinstance(inp.get(k), str)
        ]
        files = list(dict.fromkeys(files))
        _add_unique(step.files, files)
        mentions: list[str] = []
        cmd: str | None = None
        if name == "Bash":
            command = _str(inp.get("command"))
            mentions = [f for f in self.changed if f in command]
            cmd = classify_cmd(command)
            step.mentions = sorted(set(step.mentions) | set(mentions))
            if step.cmd is None or CMD_PRIORITY[cmd] > CMD_PRIORITY[step.cmd]:
                step.cmd = cmd
        if isinstance(b.get("id"), str):
            self.calls[b["id"]] = _Call(name, files, mentions, cmd)

    def user(self, msg: dict[str, Any]) -> None:
        content = msg.get("content")
        if isinstance(content, str):
            self.new("user").parts.append(content)
            return
        if not isinstance(content, list):
            return
        text_step: Step | None = None
        for b in content:
            if not isinstance(b, dict):
                continue
            kind = b.get("type")
            if kind == "tool_result":
                self.tool_result(b)
            elif kind in ("text", "image"):
                if text_step is None:
                    text_step = self.new("user")
                if kind == "text" and isinstance(b.get("text"), str):
                    text_step.parts.append(b["text"])
                elif kind == "image":
                    text_step.parts.append(_image(b))

    def tool_result(self, b: dict[str, Any]) -> None:
        step = self.new("tool_result")
        call = self.calls.get(_str(b.get("tool_use_id")))
        if call is not None:
            step.tools = [call.name]
            step.files = list(call.files)
            step.mentions = list(call.mentions)
            step.cmd = call.cmd
            if call.name == "Bash":
                step.ok = _bash_ok(b)
        content = b.get("content")
        if isinstance(content, str):
            step.parts.append(self.follow(content))
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    step.parts.append(self.follow(item["text"]))
                elif item.get("type") == "image":
                    step.parts.append(_image(item))

    def follow(self, text: str) -> str:
        """Replace a persisted-output pointer with the stored file's text."""
        if self.tr_dir is None or not text.startswith("<persisted-output>"):
            return text
        m = _POINTER.search(text)
        if m is None:
            return text
        target = os.path.normpath(m.group(1))
        if os.path.dirname(target) != self.tr_dir:
            return text
        try:
            with open(target, "rb") as fh:
                data = fh.read()
        except OSError:
            return text
        if self.aux_reads is not None:
            self.aux_reads[target] = data
        return data.decode("utf-8", errors="replace")


def parse_session(
    data: bytes,
    session: int,
    *,
    repo_root: str,
    changed_files: Sequence[str],
    main: bool = True,
    tool_results_dir: str | None = None,
    aux_reads: dict[str, bytes] | None = None,
) -> list[Step]:
    """Parse the sealed prefix of one session file into steps, in file order.

    ``main`` is True for session 0 (skips ``isSidechain`` lines). Stored
    tool-results files that were read are recorded in ``aux_reads`` (path to bytes).
    """
    p = _Parser(session, repo_root, changed_files, main, tool_results_dir, aux_reads)
    for lineno, raw in enumerate(sealed_prefix(data).split(b"\n"), start=1):
        if not raw.strip():
            continue
        try:
            d = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise SessionError(f"session {session} line {lineno}: {e}") from e
        if isinstance(d, dict):
            p.line(d)
    for s in p.steps:
        s.text = "\n".join(s.parts)
    return p.steps


def first_timestamp(data: bytes) -> str:
    """The ``timestamp`` of the first complete line, or "" (subagent sort key)."""
    head = sealed_prefix(data).split(b"\n", 1)[0]
    try:
        d = json.loads(head.decode("utf-8")) if head.strip() else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    ts = d.get("timestamp") if isinstance(d, dict) else None
    return ts if isinstance(ts, str) else ""
