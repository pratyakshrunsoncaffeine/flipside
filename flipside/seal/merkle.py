"""RFC 9162 Merkle tree over SHA-256 (docs/seal/SPEC.md, Tree).

Leaf hash: SHA-256(0x00 || salt || leaf). Node hash: SHA-256(0x01 || left || right).
Inclusion proofs follow RFC 9162 section 2.1.3.1, verification section 2.1.3.2.
"""

import hashlib
from collections.abc import Sequence


class MerkleError(ValueError):
    """Bad tree input: empty tree or an index outside the tree."""


def _sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaf_hash(salt: bytes, leaf: bytes) -> bytes:
    """L(i) = SHA-256(0x00 || salt || leaf)."""
    return _sha(b"\x00" + salt + leaf)


def node_hash(left: bytes, right: bytes) -> bytes:
    """Interior node: SHA-256(0x01 || left || right)."""
    return _sha(b"\x01" + left + right)


def _split(n: int) -> int:
    """Largest power of two strictly below n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def mth(hashes: Sequence[bytes]) -> bytes:
    """Merkle Tree Hash of already-hashed leaves. Raises MerkleError on an empty list."""
    if not hashes:
        raise MerkleError("EMPTY_SESSION: a tree needs at least one leaf")
    if len(hashes) == 1:
        return hashes[0]
    k = _split(len(hashes))
    return node_hash(mth(hashes[:k]), mth(hashes[k:]))


def inclusion_proof(m: int, hashes: Sequence[bytes]) -> list[bytes]:
    """Audit path for leaf m, ordered from the leaf up (RFC 9162 2.1.3.1)."""
    if not 0 <= m < len(hashes):
        raise MerkleError(f"leaf {m} is outside a tree of size {len(hashes)}")
    if len(hashes) == 1:
        return []
    k = _split(len(hashes))
    if m < k:
        return [*inclusion_proof(m, hashes[:k]), mth(hashes[k:])]
    return [*inclusion_proof(m - k, hashes[k:]), mth(hashes[:k])]


def proof_length(i: int, n: int) -> int:
    """Number of hashes in the inclusion proof of leaf i in a tree of size n."""
    if not 0 <= i < n:
        raise MerkleError(f"leaf {i} is outside a tree of size {n}")
    length = 0
    while n > 1:
        k = _split(n)
        if i < k:
            n = k
        else:
            i, n = i - k, n - k
        length += 1
    return length


def root_from_proof(i: int, n: int, leaf: bytes, proof: Sequence[bytes]) -> bytes | None:
    """Hash up from a leaf (RFC 9162 2.1.3.2). Returns None when the path is malformed."""
    if not 0 <= i < n:
        raise MerkleError(f"leaf {i} is outside a tree of size {n}")
    fn, sn, r = i, n - 1, leaf
    for p in proof:
        if sn == 0:
            return None
        if fn & 1 or fn == sn:
            r = node_hash(p, r)
            if not fn & 1:
                while not fn & 1 and fn != 0:
                    fn >>= 1
                    sn >>= 1
        else:
            r = node_hash(r, p)
        fn >>= 1
        sn >>= 1
    return r if sn == 0 else None


def verify_inclusion(i: int, n: int, leaf: bytes, proof: Sequence[bytes], root: bytes) -> bool:
    """True when leaf i of a size-n tree hashes up to root along proof."""
    if not 0 <= i < n:
        return False
    return root_from_proof(i, n, leaf, proof) == root
