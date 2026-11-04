"""Build synthetic Claude Code session lines for tests. All data is synthetic."""

import json
from pathlib import Path
from typing import Any


class SessionBuilder:
    """Accumulates JSONL lines shaped like Claude Code's session format."""

    def __init__(self, cwd: str, sidechain: bool = False, start: int = 0) -> None:
        self.cwd = cwd
        self.sidechain = sidechain
        self.lines: list[dict[str, Any]] = []
        self._n = start
        self._msg = 0

    def _base(self, typ: str) -> dict[str, Any]:
        self._n += 1
        return {
            "type": typ,
            "uuid": f"u{self._n}",
            "cwd": self.cwd,
            "isSidechain": self.sidechain,
            "timestamp": f"2026-11-04T10:00:{self._n % 60:02d}.000Z",
        }

    def user(self, content: Any, **extra: Any) -> "SessionBuilder":
        d = self._base("user")
        d["message"] = {"role": "user", "content": content}
        d.update(extra)
        self.lines.append(d)
        return self

    def assistant(self, *blocks: dict[str, Any], msg_id: str | None = None) -> str:
        """Write one line per block (as Claude Code does), all with one message.id."""
        if msg_id is None:
            self._msg += 1
            msg_id = f"msg_{self._msg}"
        for b in blocks:
            d = self._base("assistant")
            d["message"] = {"id": msg_id, "role": "assistant", "content": [b]}
            self.lines.append(d)
        return msg_id

    def result(self, tool_use_id: str, content: Any, is_error: bool = False) -> "SessionBuilder":
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }
        if is_error:
            block["is_error"] = True
        return self.user([block])

    def other(self, typ: str, **extra: Any) -> "SessionBuilder":
        d = self._base(typ)
        d.update(extra)
        self.lines.append(d)
        return self

    def raw(self, d: dict[str, Any]) -> "SessionBuilder":
        self.lines.append(d)
        return self

    def text(self) -> str:
        return "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in self.lines)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.text(), encoding="utf-8", newline="")
        return path


def text(t: str) -> dict[str, Any]:
    return {"type": "text", "text": t}


def tool(tid: str, name: str, **inp: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


def thinking(t: str) -> dict[str, Any]:
    return {"type": "thinking", "thinking": t, "signature": "sig"}
