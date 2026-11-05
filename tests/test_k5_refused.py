"""K5 counts only Switch's 403 as a refusal; any other error fails the run instead."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from flipside.room.switch_client import SwitchError
from flipside.room.transport import Forbidden

ROOT = Path(__file__).resolve().parents[1]


def k5() -> ModuleType:
    spec = importlib.util.spec_from_file_location("k5", ROOT / "killtests" / "k5.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Raises:
    """An ``Http`` stand-in whose PATCH raises ``error``, or succeeds when it is None."""

    def __init__(self, error: Exception | None) -> None:
        self.error = error

    def request(self, method: str, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return {}


def test_a_403_is_a_refusal() -> None:
    said = k5().refused(Raises(Forbidden("Not authorized")), "room", {"name": "x"})
    assert said.startswith("refused (Forbidden")


def test_an_accepted_change_is_not_a_refusal() -> None:
    assert k5().refused(Raises(None), "room", {"name": "x"}) == "accepted"


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_any_other_switch_error_fails_instead_of_passing(status: int) -> None:
    with pytest.raises(SwitchError):
        k5().refused(Raises(SwitchError(status, "PATCH", "/gateway/rooms/r", "boom")), "r", {})
