"""The room log: every message the gate posts or reads, kept for replay.

A judge without Slack, vendor keys or an Entire account can replay a recorded run into
a fresh local Switch room, or print it in a terminal.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

HUMAN, AGENT = "human", "agent"
COLOURS = {HUMAN: "\033[36m", AGENT: "\033[33m"}
RESET = "\033[0m"


@dataclass(frozen=True)
class RoomEvent:
    room: str
    actor: str
    kind: str
    text: str
    at: float = 0.0


class EventLog:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, room: str, actor: str, kind: str, text: str) -> RoomEvent:
        event = RoomEvent(room=room, actor=actor, kind=kind, text=text, at=time.time())
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event)) + "\n")
        return event


def read_events(path: Path) -> list[RoomEvent]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [RoomEvent(**json.loads(line)) for line in lines if line.strip()]


def print_event(event: RoomEvent, out: TextIO | None = None) -> None:
    """Human text in cyan, agent text in yellow, so the two never blur together."""
    out = out or sys.stdout
    colour = os.environ.get("NO_COLOR") is None and out.isatty()
    label = f"[{event.kind}] {event.actor}"
    if colour:
        label = f"{COLOURS.get(event.kind, '')}{label}{RESET}"
    indented = "\n".join(f"    {line}" for line in event.text.splitlines())
    print(f"{label}\n{indented}\n", file=out)
