"""G3: tests/vectors/seal_v1_1.json is reproduced by docs/seal/example.py and by flipside.seal."""

import json
import subprocess
import sys
from pathlib import Path

from flipside.seal.canon import canon
from flipside.seal.git import SealTrailer
from flipside.seal.merkle import inclusion_proof
from flipside.seal.seal import build_leaves
from flipside.seal.steps import Step
from flipside.seal.verify import check_against_seal, check_shape

ROOT = Path(__file__).resolve().parents[2]
VECTOR = ROOT / "tests" / "vectors" / "seal_v1_1.json"


def test_g3_example_reproduces_vector_byte_for_byte() -> None:
    out = subprocess.run(
        [sys.executable, str(ROOT / "docs" / "seal" / "example.py"), "--json"],
        capture_output=True,
        check=True,
    ).stdout
    assert out == VECTOR.read_bytes()


def test_g3_flipside_reproduces_vector() -> None:
    v = json.loads(VECTOR.read_text(encoding="utf-8"))
    texts = [
        "Add CSV export to the reports page.",
        "Adding export_csv() to reports/export.py.",
        "FAILED tests/test_export.py::test_export_csv - SessionExpired",
        "test_export_csv failed with SessionExpired; raising SESSION_TTL to 86400 in "
        "auth/session.py",
        "CSV export works and the tests pass.",
    ]
    steps = [
        Step(0, 0, "user", text=texts[0]),
        Step(0, 1, "assistant", ["Edit"], ["reports/export.py"], text=texts[1]),
        Step(0, 2, "tool_result", ["Bash"], [], [], "test", False, text=texts[2]),
        Step(0, 3, "assistant", ["Edit"], ["auth/session.py"], text=texts[3]),
        Step(0, 4, "assistant", text=texts[4]),
    ]
    s = build_leaves(steps, bytes.fromhex(v["key"]))
    assert s.root.hex() == v["root"]
    assert s.n == v["n"]
    assert s.manifest == v["manifest"].encode()
    assert s.manifest_sha256 == v["manifest_sha256"]
    assert [h.hex() for h in s.hashes] == v["leaf_hashes"]
    assert f"Flipside-Seal: {s.trailer.line()}" == v["trailer"]
    d = v["disclosure"]
    i = d["i"]
    assert d["leaf"] == s.leaves[i]
    assert d["salt"] == s.salts[i].hex()
    assert d["proof"] == [h.hex() for h in inclusion_proof(i, s.hashes)]
    assert check_shape(d) is None
    t = SealTrailer(v["root"], v["n"], v["manifest_sha256"])
    assert check_against_seal(d, s.manifest, t).code == "OK"


def test_vector_disclosure_is_canonical_json_safe() -> None:
    d = json.loads(VECTOR.read_text(encoding="utf-8"))["disclosure"]
    assert canon(d)
