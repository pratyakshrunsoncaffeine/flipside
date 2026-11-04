"""Prove and verify end to end in temp git repos. Gates G2, G5 and G6 live here."""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from flipside.seal.git import SealTrailer
from flipside.seal.manifest import load_manifest
from flipside.seal.prove import ProveError, leaf_secret_hits, prove, rebuild
from flipside.seal.seal import SealResult, seal
from flipside.seal.verify import check_against_seal, check_shape, verify
from tests.seal.builder import text, tool
from tests.seal.conftest import PR, run


def ttl_leaf(res: SealResult) -> int:
    """Index of the leaf that holds "86400" in the auth/session.py edit step."""
    return next(
        i
        for i, lf in enumerate(res.sealed.leaves)
        if "auth/session.py" in lf["files"] and lf["role"] == "assistant" and "86400" in lf["text"]
    )


@pytest.fixture
def sealed(pr: PR) -> tuple[PR, SealResult]:
    return pr, seal(pr.repo, pr.session, "main")


def test_ok_round_trip_every_leaf(sealed: tuple[PR, SealResult]) -> None:
    pr, res = sealed
    assert res.commit
    manifest = res.manifest_path.read_bytes()
    for i in range(res.sealed.n):
        d = prove(pr.repo, res.sealed.root.hex(), i)
        v = verify(pr.repo, d, manifest, commit=res.commit)
        assert v.code == "OK", (i, v)
    i = ttl_leaf(res)
    v = verify(pr.repo, prove(pr.repo, res.sealed.root.hex(), i), manifest, commit=res.commit)
    lf = res.sealed.leaves[i]
    assert v.message() == (
        f"OK leaf {i} (session 0, step {lf['step']}, chunk {lf['chunk']}) "
        f"against seal {res.sealed.root.hex()[:7]} in commit "
        f"{res.commit[:7]}"
    )


def test_disclosure_shape(sealed: tuple[PR, SealResult]) -> None:
    pr, res = sealed
    d = prove(pr.repo, res.sealed.root.hex(), 0)
    assert sorted(d) == sorted(["v", "commit", "i", "n", "salt", "leaf", "proof"])
    assert d["n"] == res.sealed.n and d["commit"] == res.commit
    assert check_shape(d) is None
    assert check_shape({**d, "t": "disclosure", "q": 1}) is None


# --- G2: single-bit flips -------------------------------------------------------


def _flip_hex(h: str, bit: int) -> str:
    b = bytearray(bytes.fromhex(h))
    b[bit // 8] ^= 1 << (bit % 8)
    return b.hex()


def test_g2_single_bit_flips(sealed: tuple[PR, SealResult]) -> None:
    """G2: flipping any single bit of text, salt, a sibling, the index, n or the root fails."""
    pr, res = sealed
    assert res.commit
    manifest = res.manifest_path.read_bytes()
    trailer = res.sealed.trailer
    i = ttl_leaf(res)
    good = prove(pr.repo, trailer.root, i)
    assert check_against_seal(good, manifest, trailer).code == "OK"

    def code(d: dict[str, Any], t: SealTrailer = trailer) -> str:
        reason = check_shape(d)
        return "BAD_DISCLOSURE" if reason else check_against_seal(d, manifest, t).code

    flips = 0
    for pos, ch in enumerate(good["leaf"]["text"]):
        for bit in range(7):
            d = copy.deepcopy(good)
            t = d["leaf"]["text"]
            d["leaf"]["text"] = t[:pos] + chr(ord(ch) ^ (1 << bit)) + t[pos + 1 :]
            assert code(d) == "PROOF_FAIL", (pos, bit)
            flips += 1
    for bit in range(256):
        d = copy.deepcopy(good)
        d["salt"] = _flip_hex(d["salt"], bit)
        assert code(d) == "PROOF_FAIL"
        for k in range(len(good["proof"])):
            d = copy.deepcopy(good)
            d["proof"][k] = _flip_hex(d["proof"][k], bit)
            assert code(d) == "PROOF_FAIL"
        t = SealTrailer(_flip_hex(trailer.root, bit), trailer.n, trailer.manifest)
        assert code(good, t) == "PROOF_FAIL"
        flips += 2 + len(good["proof"])
    for bit in range(12):
        d = copy.deepcopy(good)
        d["i"] ^= 1 << bit
        assert code(d) in ("MANIFEST_MISMATCH", "BAD_SIZE"), bit
        d = copy.deepcopy(good)
        d["n"] ^= 1 << bit
        assert code(d) == "BAD_SIZE", bit
    for field, value in (
        ("step", good["leaf"]["step"] + 1),
        ("ok", True),
        ("cmd", "test"),
        ("files", []),
        ("mentions", ["x"]),
        ("role", "user"),
    ):
        d = copy.deepcopy(good)
        d["leaf"][field] = value
        assert code(d) == "MANIFEST_MISMATCH", field
    assert flips > 2000


def test_index_flip_codes_are_specific(sealed: tuple[PR, SealResult]) -> None:
    pr, res = sealed
    manifest = res.manifest_path.read_bytes()
    good = prove(pr.repo, res.sealed.root.hex(), 3)
    assert (
        check_against_seal({**good, "i": 2}, manifest, res.sealed.trailer).code
        == "MANIFEST_MISMATCH"
    )
    assert (
        check_against_seal({**good, "i": 3 + 4096}, manifest, res.sealed.trailer).code == "BAD_SIZE"
    )
    assert (
        check_against_seal({**good, "proof": good["proof"][:-1]}, manifest, res.sealed.trailer).code
        == "BAD_SIZE"
    )


def test_manifest_hash(sealed: tuple[PR, SealResult]) -> None:
    pr, res = sealed
    assert res.commit
    d = prove(pr.repo, res.sealed.root.hex(), 0)
    m = res.manifest_path.read_bytes()
    assert verify(pr.repo, d, m + b" ", commit=res.commit).code == "MANIFEST_HASH"
    entries = load_manifest(m)
    entries[0]["ok"] = True
    forged = json.dumps(entries).encode()
    assert verify(pr.repo, d, forged, commit=res.commit).code == "MANIFEST_HASH"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("salt"),
        lambda d: d.update(salt="zz" * 32),
        lambda d: d.update(i=True),
        lambda d: d.update(i=-1),
        lambda d: d.update(commit="ABC"),
        lambda d: d.update(proof="x"),
        lambda d: d["leaf"].update(extra=1),
        lambda d: d["leaf"].update(text=5),
        lambda d: d["leaf"].update(step=1.5),
        lambda d: d.update(v=2),
    ],
)
def test_bad_disclosure(sealed: tuple[PR, SealResult], mutate: Any) -> None:
    pr, res = sealed
    assert res.commit
    d = prove(pr.repo, res.sealed.root.hex(), 0)
    mutate(d)
    assert (
        verify(pr.repo, d, res.manifest_path.read_bytes(), commit=res.commit).code
        == "BAD_DISCLOSURE"
    )


def test_not_a_dict_is_bad_disclosure(sealed: tuple[PR, SealResult]) -> None:
    pr, _res = sealed
    assert verify(pr.repo, [1], b"", commit="HEAD").code == "BAD_DISCLOSURE"


def test_no_seal_and_not_in_pr(sealed: tuple[PR, SealResult]) -> None:
    pr, res = sealed
    assert res.commit
    m = res.manifest_path.read_bytes()
    d = prove(pr.repo, res.sealed.root.hex(), 0)
    assert verify(pr.repo, d, m, commit="HEAD~1").code == "NO_SEAL"
    assert verify(pr.repo, d, m, commit="f" * 40).code == "NO_SEAL"
    assert verify(pr.repo, d, m, commit=res.commit, head="main").code == "NOT_IN_PR"
    run(
        pr.repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "two seals",
        "--trailer",
        "Flipside-Seal: v1 root=" + "a" * 64 + " n=1 manifest=" + "b" * 64,
        "--trailer",
        "Flipside-Seal: v1 root=" + "c" * 64 + " n=1 manifest=" + "d" * 64,
    )
    two = run(pr.repo, "rev-parse", "HEAD").strip()
    assert verify(pr.repo, {**d, "commit": two}, m, commit=two).code == "NO_SEAL"
    run(
        pr.repo,
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "bad",
        "--trailer",
        "Flipside-Seal: v2 root=zz",
    )
    bad = run(pr.repo, "rev-parse", "HEAD").strip()
    assert verify(pr.repo, {**d, "commit": bad}, m, commit=bad).code == "NO_SEAL"


# --- G5 ---------------------------------------------------------------------------


def test_g5_edited_quote_resealed_and_edited_session(sealed: tuple[PR, SealResult]) -> None:
    """G5: edited quote PROOF_FAIL; re-seal after the question WRONG_COMMIT;
    edited earlier line SESSION_CHANGED."""
    pr, res = sealed
    assert res.commit
    question_commit = res.commit
    i = ttl_leaf(res)
    manifest = res.manifest_path.read_bytes()
    d = prove(pr.repo, res.sealed.root.hex(), i)
    assert verify(pr.repo, d, manifest, commit=question_commit).code == "OK"

    forged = copy.deepcopy(d)
    forged["leaf"]["text"] = forged["leaf"]["text"].replace("86400", "3600")
    assert verify(pr.repo, forged, manifest, commit=question_commit).code == "PROOF_FAIL"

    text_now = pr.session.read_text(encoding="utf-8")
    pr.session.write_text(
        text_now.replace("raising SESSION_TTL to 86400", "keeping SESSION_TTL at 3600"),
        encoding="utf-8",
        newline="",
    )
    with pytest.raises(ProveError) as e:
        prove(pr.repo, res.sealed.root.hex(), i)
    assert e.value.code == "SESSION_CHANGED"

    res2 = seal(pr.repo, pr.session, "main")
    assert res2.commit and res2.commit != question_commit
    d2 = prove(pr.repo, res2.sealed.root.hex(), ttl_leaf_or_any(res2))
    v = verify(pr.repo, d2, res2.manifest_path.read_bytes(), commit=question_commit)
    assert v.code == "WRONG_COMMIT"
    v = verify(pr.repo, d2, manifest, commit=question_commit)
    assert v.code == "WRONG_COMMIT"


def ttl_leaf_or_any(res: SealResult) -> int:
    return next(
        (
            i
            for i, lf in enumerate(res.sealed.leaves)
            if "auth/session.py" in lf["files"] and lf["role"] == "assistant"
        ),
        0,
    )


def test_tool_results_file_change_is_session_changed(pr: PR) -> None:
    tr = pr.session.with_suffix("") / "tool-results"
    tr.mkdir(parents=True)
    big = tr / "big.txt"
    big.write_text("FULL OUTPUT", encoding="utf-8", newline="")
    pr.builder.assistant(tool("t8", "Bash", command="cat log"))
    pr.builder.result("t8", f"<persisted-output>\nFull output saved to: {big}\n</persisted-output>")
    pr.builder.write(pr.session)
    res = seal(pr.repo, pr.session, "main")
    assert any(lf["text"] == "FULL OUTPUT" for lf in res.sealed.leaves)
    prove(pr.repo, res.sealed.root.hex(), 0)
    big.write_text("CHANGED", encoding="utf-8", newline="")
    with pytest.raises(ProveError) as e:
        prove(pr.repo, res.sealed.root.hex(), 0)
    assert e.value.code == "SESSION_CHANGED"


# --- G6 ---------------------------------------------------------------------------


def test_g6_appending_after_seal_is_not_session_changed(sealed: tuple[PR, SealResult]) -> None:
    """G6 (F1): bytes appended after the seal are expected and ignored."""
    pr, res = sealed
    assert res.commit
    pr.builder.assistant(text("More work after the seal."))
    pr.builder.write(pr.session)
    with pr.session.open("ab") as fh:
        fh.write(b'{"type":"assistant","message":{"id":"partial"')
    i = ttl_leaf(res)
    d = prove(pr.repo, res.sealed.root.hex(), i)
    assert verify(pr.repo, d, res.manifest_path.read_bytes(), commit=res.commit).code == "OK"


def test_deleted_session_is_session_changed(sealed: tuple[PR, SealResult]) -> None:
    pr, res = sealed
    pr.session.unlink()
    with pytest.raises(ProveError) as e:
        prove(pr.repo, res.sealed.root.hex(), 0)
    assert e.value.code == "SESSION_CHANGED"


def test_prove_errors(sealed: tuple[PR, SealResult]) -> None:
    pr, res = sealed
    with pytest.raises(ProveError) as e:
        prove(pr.repo, "0" * 64, 0)
    assert e.value.code == "NO_STATE"
    with pytest.raises(ProveError) as e:
        prove(pr.repo, res.sealed.root.hex(), res.sealed.n)
    assert e.value.code == "BAD_LEAF"


def test_secret_split_across_chunks_is_caught(pr: PR) -> None:
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    pr.builder.assistant(text("x" * 290 + "=" + token))
    pr.builder.write(pr.session)
    res = seal(pr.repo, pr.session, "main", commit=False)
    rb = rebuild(pr.repo, res.sealed.root.hex())
    idx = [
        i
        for i, lf in enumerate(res.sealed.leaves)
        if lf["text"].startswith("x" * 290) or (lf["chunk"] == 1 and lf["text"] in token)
    ]
    assert len(idx) == 2
    for i in idx:
        assert [h.kind for h in leaf_secret_hits(rb, i)] == ["github_token"]
    assert leaf_secret_hits(rb, 0) == []


def test_state_holds_no_text(sealed: tuple[PR, SealResult]) -> None:
    _, res = sealed
    body = res.state_path.read_text(encoding="utf-8")
    assert "SessionExpired" not in body and "CSV export" not in body
    assert Path(json.loads(body)["sessions"][0]["path"]).name == "sess-1.jsonl"
