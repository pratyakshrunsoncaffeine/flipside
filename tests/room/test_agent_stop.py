"""Agent processes stop through their shutdown path on every OS (stop file, not a signal)."""

import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from flipside.room import daemon
from flipside.room.solo import Agents

# Stands in for `flip agent`: serves until its stop file appears, then exits 0.
CHILD = (
    "import pathlib, sys, time\n"
    "stop = pathlib.Path(sys.argv[1])\n"
    "while not stop.exists():\n"
    "    time.sleep(0.05)\n"
    "print('stopped', flush=True)\n"
)


def test_stop_all_lets_each_agent_run_its_shutdown_path(tmp_path: Path) -> None:
    lines: list[str] = []
    agents = Agents({}, tmp_path, lines.append)
    for role in ("author", "reviewer"):
        agents.procs[role] = subprocess.Popen(
            [sys.executable, "-c", CHILD, str(agents.stop_file(role))]
        )
    agents.stop_all()
    assert [p.returncode for p in agents.procs.values()] == [0, 0]
    assert lines == [
        "author-agent process exited with 0",
        "reviewer-agent process exited with 0",
    ]


def test_run_stops_on_the_stop_file_and_flushes_its_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged: list[str] = []
    closed = threading.Event()
    transport = SimpleNamespace(close=closed.set, tap=SimpleNamespace(notes=["event stream gap"]))
    agent = SimpleNamespace(step=lambda: None)
    monkeypatch.setattr(daemon, "prepare_work", lambda cfg: None)
    monkeypatch.setattr(daemon, "author", lambda cfg: (agent, transport))
    monkeypatch.setattr(daemon, "log", logged.append)
    stop_file = tmp_path / "author-agent.stop"
    cfg: dict[str, Any] = {"role": "author", "agent_name": "a"}
    done: list[int] = []
    t = threading.Thread(
        target=lambda: done.append(daemon.run(cfg, threading.Event(), 0.01, stop_file))
    )
    t.start()
    stop_file.touch()
    t.join(5)
    assert done == [0]
    assert closed.is_set()
    assert logged[-2:] == ["a: event stream gap", "a stopped"]
