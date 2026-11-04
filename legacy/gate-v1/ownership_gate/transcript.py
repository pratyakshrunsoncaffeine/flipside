"""Reads a Claude Code session transcript into numbered steps.

Claude Code writes one JSON record per line. Prompts are `user` records with text
content; tool calls are `tool_use` blocks in `assistant` records, and their results are
`tool_result` blocks in later `user` records, flagged `is_error` when the call failed.
Entire stores this same raw transcript as `full.jsonl` in each checkpoint.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
SKIPPED_PROMPT_PREFIXES = (
    "<system-reminder>",
    "<local-command",
    "<command-",
    "<task-notification>",
    "[Request interrupted",
    "Caveat:",
)
# Error results for calls that never ran: the user rejected or interrupted them, a
# permission rule or hook denied them, or the input was invalid.
NOT_RUN_PREFIXES = (
    "The user doesn't want to proceed",
    "Permission for this",
    "Permission to use",
    "[Request interrupted",
    "<tool_use_error>",
)


class StepKind(StrEnum):
    PROMPT = "prompt"
    BASH = "bash"
    EDIT = "edit"


@dataclass(frozen=True)
class Step:
    """One numbered event in a session. `ok` is None when a command has no recorded result."""

    index: int
    kind: StepKind
    text: str = ""
    command: str = ""
    path: str = ""
    ok: bool | None = None
    output: str = ""


@dataclass(frozen=True)
class Session:
    steps: tuple[Step, ...]

    def prompts(self) -> list[Step]:
        return [s for s in self.steps if s.kind is StepKind.PROMPT]

    def commands(self) -> list[Step]:
        return [s for s in self.steps if s.kind is StepKind.BASH]

    def edited_paths(self) -> set[str]:
        return {s.path for s in self.steps if s.kind is StepKind.EDIT and s.path}


def parse_claude_code(lines: Iterable[str]) -> Session:
    records = [r for r in (_load(line) for line in lines) if r is not None and _in_main_thread(r)]
    results = _tool_results(records)
    steps: list[Step] = []
    for record in records:
        for draft in _drafts(record, results):
            steps.append(Step(index=len(steps) + 1, **draft))
    return Session(steps=tuple(steps))


def _load(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def _in_main_thread(record: dict[str, Any]) -> bool:
    return (
        record.get("type") in ("user", "assistant")
        and not record.get("isSidechain")
        and not record.get("isMeta")
        and isinstance(record.get("message"), dict)
    )


def _blocks(record: dict[str, Any]) -> list[dict[str, Any]]:
    content = record["message"].get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _tool_results(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        block["tool_use_id"]: block
        for record in records
        if record["type"] == "user"
        for block in _blocks(record)
        if block.get("type") == "tool_result" and "tool_use_id" in block
    }


def _drafts(record: dict[str, Any], results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = _blocks(record)
    if record["type"] == "user":
        prompt = _prompt_text(blocks)
        return [{"kind": StepKind.PROMPT, "text": prompt}] if prompt else []
    return [d for d in (_tool_draft(b, results) for b in blocks) if d is not None]


def _prompt_text(blocks: list[dict[str, Any]]) -> str:
    if any(b.get("type") == "tool_result" for b in blocks):
        return ""
    texts = [
        b["text"].strip()
        for b in blocks
        if b.get("type") == "text" and isinstance(b.get("text"), str)
    ]
    texts = [t for t in texts if t and not t.startswith(SKIPPED_PROMPT_PREFIXES)]
    return "\n".join(texts)


def _tool_draft(block: dict[str, Any], results: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if block.get("type") != "tool_use":
        return None
    name = block.get("name")
    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
    result = results.get(block.get("id", ""))
    failed = result is not None and bool(result.get("is_error", False))
    output = "" if result is None else _flatten(result.get("content"))
    if name == "Bash":
        ran = result is not None and not (failed and output.lstrip().startswith(NOT_RUN_PREFIXES))
        return {
            "kind": StepKind.BASH,
            "command": str(tool_input.get("command", "")),
            "ok": not failed if ran else None,
            "output": output,
        }
    if name in EDIT_TOOLS and not failed:
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
        return {"kind": StepKind.EDIT, "path": str(path)}
    return None


def _flatten(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""
