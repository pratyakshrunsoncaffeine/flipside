"""Offline scenarios: a PR, its session transcript, and the author's scripted answers.

Each scenario folder holds `pr.json`, an optional `full.jsonl` (no file means no trail),
and `answers.json` (a list of `{"sender": ..., "text": ...}`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ownership_gate.controller import GateController
from ownership_gate.entire import load_transcript_file
from ownership_gate.events import AGENT, HUMAN, EventLog, RoomEvent
from ownership_gate.model import ChangedFile, CheckRun, PullRequest

GATE_ACTOR = "ownership-gate"


@dataclass(frozen=True)
class Scenario:
    pr: PullRequest
    transcript: Path | None
    answers: tuple[dict[str, str], ...]
    reviewer: str


def load_pr(path: Path) -> PullRequest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PullRequest(
        repo=raw["repo"],
        number=raw["number"],
        author=raw["author"],
        title=raw.get("title", ""),
        body=raw.get("body", ""),
        head_sha=raw.get("head_sha", "0000000"),
        files=tuple(ChangedFile(**f) for f in raw.get("files", [])),
        checks=tuple(CheckRun(**c) for c in raw.get("checks", [])),
        checkpoint_ids=tuple(raw.get("checkpoint_ids", [])),
    )


def load_scenario(folder: Path) -> Scenario:
    transcript = folder / "full.jsonl"
    answers_file = folder / "answers.json"
    meta = json.loads((folder / "pr.json").read_text(encoding="utf-8"))
    answers = json.loads(answers_file.read_text(encoding="utf-8")) if answers_file.exists() else []
    return Scenario(
        pr=load_pr(folder / "pr.json"),
        transcript=transcript if transcript.exists() else None,
        answers=tuple(answers),
        reviewer=meta.get("reviewer", ""),
    )


def run_scenario(scenario: Scenario, log: EventLog) -> list[RoomEvent]:
    """Play the scenario through the real controller and return the room log."""
    room = f"pr-{scenario.pr.repo.replace('/', '-')}-{scenario.pr.number}".lower()
    session = None if scenario.transcript is None else load_transcript_file(scenario.transcript)
    ctl = GateController(reviewer=scenario.reviewer)
    events = [log.add(room, GATE_ACTOR, AGENT, m) for m in ctl.open(scenario.pr, session)]
    for answer in scenario.answers:
        events.append(log.add(room, answer["sender"], HUMAN, answer["text"]))
        replies = ctl.on_message(scenario.pr.key, answer["sender"], answer["text"])
        events += [log.add(room, GATE_ACTOR, AGENT, m) for m in replies]
    return events
