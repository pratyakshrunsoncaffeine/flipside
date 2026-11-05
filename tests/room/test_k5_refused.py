"""K5.g and K5.h pass only on Switch's 403, never on another server error."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from flipside.room.switch_client import SwitchError
from flipside.room.transport import Forbidden

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("k5", ROOT / "killtests" / "k5.py")
assert spec and spec.loader
k5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(k5)


class _Http:
    def __init__(self, err: Exception | None) -> None:
        self.err = err

    def request(self, method: str, path: str, body: Any = None) -> Any:
        if self.err:
            raise self.err
        return {}


def test_a_403_is_a_refusal() -> None:
    said = k5.refused(_Http(Forbidden("Not authorized to write this resource")), "r1", {})
    assert said.startswith("refused (Forbidden")


def test_a_server_error_is_not_a_refusal() -> None:
    with pytest.raises(SwitchError):
        k5.refused(_Http(SwitchError(500, "PATCH", "/gateway/rooms/r1", "boom")), "r1", {})


def test_an_accepted_change_is_reported() -> None:
    assert k5.refused(_Http(None), "r1", {}) == "accepted"
