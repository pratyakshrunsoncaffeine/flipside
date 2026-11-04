"""Agent process config: permissions, PR data, defaults (synthetic values)."""

import os
from pathlib import Path

import pytest

from flipside.room.daemon import load_config, pr_data, reviewer_head, write_config
from flipside.room.rules import CheckRun


def test_config_is_written_private_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    write_config(path, {"role": "author", "api_key": "synthetic"})
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert load_config(path)["role"] == "author"


def test_a_config_readable_by_others_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    write_config(path, {"role": "author"})
    os.chmod(path, 0o644)
    with pytest.raises(SystemExit, match="chmod 600"):
        load_config(path)


def test_pr_data_from_the_config() -> None:
    pr = pr_data(
        {
            "pr": {
                "number": 7,
                "title": "t",
                "body": "b",
                "author": "a",
                "files": ["x.py"],
                "checks": [{"name": "ci", "conclusion": "failure"}],
            }
        }
    )
    assert (pr.number, pr.files, pr.checks) == (7, ("x.py",), (CheckRun("ci", "failure"),))


def test_reviewer_head_needs_a_head_or_github() -> None:
    assert reviewer_head({"head": "abc"}) == "abc"
    with pytest.raises(SystemExit):
        reviewer_head({})
