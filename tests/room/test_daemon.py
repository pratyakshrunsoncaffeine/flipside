"""Agent process config: permissions, PR data, defaults (synthetic values)."""

import os
from pathlib import Path

import pytest

from flipside.room.daemon import (
    COMMON_KEYS,
    ROLE_KEYS,
    load_config,
    pr_data,
    reviewer_head,
    write_config,
)
from flipside.room.rules import CheckRun


def test_config_is_written_private_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "agent.json"
    cfg = {k: "synthetic" for k in (*COMMON_KEYS, *ROLE_KEYS["author"])}
    write_config(path, {**cfg, "role": "author", "pr_number": 1})
    if os.name == "posix":
        assert os.stat(path).st_mode & 0o777 == 0o600
    assert load_config(path)["role"] == "author"


@pytest.mark.skipif(os.name != "posix", reason="Windows has no POSIX mode bits")
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


def test_work_dir_is_created_private(tmp_path: Path) -> None:
    # Found on a real PR: flip setup's default work dir did not exist, so every state
    # save failed and author-agent reopened its cards on each step.
    from flipside.room.daemon import prepare_work

    work = tmp_path / "repo" / ".git" / "flipside" / "work-author"
    prepare_work({"work": str(work)})
    assert work.is_dir()
    if os.name == "posix":
        assert os.stat(work).st_mode & 0o777 == 0o700
    prepare_work({"work": str(work)})  # idempotent
