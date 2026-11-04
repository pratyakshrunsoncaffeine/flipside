"""Builds Claude Code transcript lines for tests, in the shape Claude Code writes them."""

from __future__ import annotations

import itertools
import json
from typing import Any


class SessionBuilder:
    def __init__(self) -> None:
        self._lines: list[dict[str, Any]] = []
        self._ids = itertools.count(1)

    def prompt(self, text: str) -> SessionBuilder:
        self._lines.append(
            {"type": "user", "isSidechain": False, "message": {"role": "user", "content": text}}
        )
        return self

    def bash(self, command: str, *, ok: bool = True, output: str = "") -> SessionBuilder:
        return self._tool("Bash", {"command": command}, ok=ok, output=output)

    def edit(self, path: str, *, ok: bool = True, output: str = "") -> SessionBuilder:
        tool_input = {"file_path": path, "old_string": "a", "new_string": "b"}
        return self._tool("Edit", tool_input, ok=ok, output=output)

    def write(self, path: str) -> SessionBuilder:
        return self._tool("Write", {"file_path": path, "content": "x"})

    def _tool(
        self, name: str, tool_input: dict[str, Any], *, ok: bool = True, output: str = ""
    ) -> SessionBuilder:
        tool_id = f"toolu_{next(self._ids):04d}"
        self._lines.append(
            {
                "type": "assistant",
                "isSidechain": False,
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input},
                    ],
                },
            }
        )
        result: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_id, "content": output}
        if not ok:
            result["is_error"] = True
        self._lines.append(
            {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [result]}}
        )
        return self

    def lines(self) -> list[str]:
        return [json.dumps(line) for line in self._lines]

    def text(self) -> str:
        return "\n".join(self.lines()) + "\n"
