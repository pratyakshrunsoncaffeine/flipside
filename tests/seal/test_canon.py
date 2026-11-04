"""Canonical JSON (docs/seal/SPEC.md, Leaves)."""

import pytest

from flipside.seal.canon import CanonError, canon, canon_text


def test_sorted_keys_no_spaces_utf8() -> None:
    assert canon({"b": 1, "a": [True, None, "é"]}) == '{"a":[true,null,"é"],"b":1}'.encode()


def test_nested_objects_sorted() -> None:
    assert canon({"z": {"y": 1, "x": 2}}) == b'{"z":{"x":2,"y":1}}'


def test_non_ascii_is_raw_utf8() -> None:
    assert canon("日本") == '"日本"'.encode()


@pytest.mark.parametrize("bad", [1.5, {"a": 0.0}, [1, [2.0]], float("nan")])
def test_floats_raise(bad: object) -> None:
    with pytest.raises(CanonError):
        canon(bad)


@pytest.mark.parametrize("bad", [(1, 2), {1: "a"}, b"x", {"a": {1, 2}}])
def test_other_types_raise(bad: object) -> None:
    with pytest.raises(CanonError):
        canon(bad)


def test_bool_is_not_int() -> None:
    assert canon([True, 1]) == b"[true,1]"


def test_canon_text_allows_floats_for_step_text() -> None:
    assert canon_text({"scale": 0.6, "a": 1}) == '{"a":1,"scale":0.6}'


def test_canon_text_rejects_nan() -> None:
    with pytest.raises(CanonError):
        canon_text({"x": float("inf")})
