"""The pull request as the gate sees it, independent of where it was fetched from."""

from __future__ import annotations

from dataclasses import dataclass, field

FAILED_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
)


@dataclass(frozen=True)
class ChangedFile:
    path: str
    additions: int = 0
    deletions: int = 0


@dataclass(frozen=True)
class CheckRun:
    """A CI result for the head commit. `conclusion` is None while the run is in progress."""

    name: str
    conclusion: str | None

    @property
    def failed(self) -> bool:
        return self.conclusion in FAILED_CONCLUSIONS

    @property
    def passed(self) -> bool:
        return self.conclusion == "success"


@dataclass(frozen=True)
class PullRequest:
    repo: str
    number: int
    author: str
    title: str
    body: str
    head_sha: str
    files: tuple[ChangedFile, ...] = ()
    checks: tuple[CheckRun, ...] = ()
    checkpoint_ids: tuple[str, ...] = field(default=())

    @property
    def key(self) -> str:
        return f"{self.repo}#{self.number}"
