"""Reference maths for flip seal v1.1 (docs/seal/SPEC.md). Standard library only.

Independent of the flipside package on purpose: tests check that both produce
tests/vectors/seal_v1_1.json byte for byte. Demo key: 32 zero bytes.

    python3 docs/seal/example.py          # human-readable summary
    python3 docs/seal/example.py --json   # the pinned vector file, exactly
"""

import hashlib
import hmac
import json
import sys
import unicodedata
from typing import Any


def sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def canon(o: Any) -> bytes:
    return json.dumps(
        o, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def chunks(t: str, n: int = 300) -> list[str]:
    t = unicodedata.normalize("NFC", t.replace("\r\n", "\n"))
    out = []
    while len(t) > n:
        cut = max(t.rfind(" ", 0, n), t.rfind("\n", 0, n))  # inside the first n code points
        cut = cut + 1 if cut >= 0 else n
        out.append(t[:cut])
        t = t[cut:]
    out.append(t)
    return out


def leaf_hash(salt: bytes, leaf: dict[str, Any]) -> bytes:
    return sha(b"\x00" + salt + canon(leaf))


def split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def mth(hs: list[bytes]) -> bytes:
    if len(hs) == 1:
        return hs[0]
    k = split(len(hs))
    return sha(b"\x01" + mth(hs[:k]) + mth(hs[k:]))


def path(m: int, hs: list[bytes]) -> list[bytes]:
    if len(hs) == 1:
        return []
    k = split(len(hs))
    return [*path(m, hs[:k]), mth(hs[k:])] if m < k else [*path(m - k, hs[k:]), mth(hs[:k])]


def verify(i: int, n: int, lh: bytes, p: list[bytes], root: bytes) -> bool:  # RFC 9162 2.1.3.2
    if i >= n:
        return False
    fn, sn, r = i, n - 1, lh
    for s in p:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            r = sha(b"\x01" + s + r)
            if not fn & 1:
                while fn & 1 == 0 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = sha(b"\x01" + r + s)
        fn >>= 1
        sn >>= 1
    return sn == 0 and r == root


KEY = bytes(32)  # demo key only
COMMIT = "a41b2c7" + "0" * 33  # placeholder seal commit for the vector
DISCLOSE = 3
# (role, tools, files, mentions, cmd, ok, text)
STEPS: list[tuple[str, list[str], list[str], list[str], str | None, bool | None, str]] = [
    ("user", [], [], [], None, None, "Add CSV export to the reports page."),
    (
        "assistant",
        ["Edit"],
        ["reports/export.py"],
        [],
        None,
        None,
        "Adding export_csv() to reports/export.py.",
    ),
    (
        "tool_result",
        ["Bash"],
        [],
        [],
        "test",
        False,
        "FAILED tests/test_export.py::test_export_csv - SessionExpired",
    ),
    (
        "assistant",
        ["Edit"],
        ["auth/session.py"],
        [],
        None,
        None,
        "test_export_csv failed with SessionExpired; raising SESSION_TTL to 86400 in "
        "auth/session.py",
    ),
    ("assistant", [], [], [], None, None, "CSV export works and the tests pass."),
]


def build() -> dict[str, Any]:
    leaves: list[dict[str, Any]] = []
    for s, (role, tools, files, mentions, cmd, ok, text) in enumerate(STEPS):
        for c, t in enumerate(chunks(text)):
            leaves.append(
                {
                    "v": 1,
                    "session": 0,
                    "step": s,
                    "chunk": c,
                    "role": role,
                    "tools": tools,
                    "files": files,
                    "mentions": mentions,
                    "cmd": cmd,
                    "ok": ok,
                    "text": t,
                }
            )
    manifest = canon(
        [{"i": i, **{k: v for k, v in lf.items() if k != "text"}} for i, lf in enumerate(leaves)]
    )
    salts = [
        hmac.new(
            KEY, b"flipside/salt/v1" + canon([lf["session"], lf["step"], lf["chunk"]]), "sha256"
        ).digest()
        for lf in leaves
    ]
    hs = [leaf_hash(salts[i], lf) for i, lf in enumerate(leaves)]
    root = mth(hs)
    i = DISCLOSE
    return {
        "key": KEY.hex(),
        "n": len(leaves),
        "root": root.hex(),
        "manifest": manifest.decode(),
        "manifest_sha256": sha(manifest).hex(),
        "leaf_hashes": [h.hex() for h in hs],
        "trailer": f"Flipside-Seal: v1 root={root.hex()} n={len(leaves)} "
        f"manifest={sha(manifest).hex()}",
        "disclosure": {
            "v": 1,
            "commit": COMMIT,
            "i": i,
            "n": len(leaves),
            "salt": salts[i].hex(),
            "leaf": leaves[i],
            "proof": [p.hex() for p in path(i, hs)],
        },
    }


def vector_bytes() -> bytes:
    return (json.dumps(build(), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def main() -> None:
    if sys.argv[1:] == ["--json"]:
        sys.stdout.buffer.write(vector_bytes())
        return
    v = build()
    d = v["disclosure"]
    root = bytes.fromhex(v["root"])
    hs = [bytes.fromhex(h) for h in v["leaf_hashes"]]
    proof = [bytes.fromhex(p) for p in d["proof"]]
    i, n = d["i"], d["n"]
    print("n", n, "root", v["root"])
    print("manifest", v["manifest_sha256"])
    print("proof len", len(proof), [p.hex()[:12] for p in proof])
    print("verify ok", verify(i, n, hs[i], proof, root))
    bad = dict(d["leaf"], text=d["leaf"]["text"].replace("86400", "3600"))
    print("tamper", verify(i, n, leaf_hash(bytes.fromhex(d["salt"]), bad), proof, root))
    print("wrong idx", verify(2, n, hs[i], proof, root))
    ok = all(
        verify(j, m, h[j], path(j, h), mth(h))
        for m in range(1, 70)
        for h in [[sha(bytes([x])) for x in range(m)]]
        for j in range(m)
    )
    print("all sizes 1..69 ok", ok)
    print(len(chunks("a" * 650)), [len(x) for x in chunks("word " * 130)])


if __name__ == "__main__":
    main()
