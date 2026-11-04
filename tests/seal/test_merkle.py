"""RFC 9162 Merkle tree (docs/seal/SPEC.md, Tree). Gate G1 lives here."""

import hashlib

import pytest

from flipside.seal.merkle import (
    MerkleError,
    inclusion_proof,
    leaf_hash,
    mth,
    node_hash,
    proof_length,
    root_from_proof,
    verify_inclusion,
)


def h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def leaves(n: int) -> list[bytes]:
    return [h(i.to_bytes(4, "big")) for i in range(n)]


def test_leaf_and_node_prefixes() -> None:
    salt, data = b"s" * 32, b'{"a":1}'
    assert leaf_hash(salt, data) == h(b"\x00" + salt + data)
    assert node_hash(b"l", b"r") == h(b"\x01lr")


def test_empty_tree_is_an_error() -> None:
    with pytest.raises(MerkleError):
        mth([])


def test_known_shapes() -> None:
    a, b, c = leaves(3)
    assert mth([a]) == a
    assert mth([a, b]) == node_hash(a, b)
    assert mth([a, b, c]) == node_hash(node_hash(a, b), c)


def test_rfc9162_split_is_largest_power_of_two_below_n() -> None:
    ls = leaves(5)
    assert mth(ls) == node_hash(mth(ls[:4]), ls[4])
    ls = leaves(8)
    assert mth(ls) == node_hash(mth(ls[:4]), mth(ls[4:]))


def test_g1_every_leaf_every_size_1_to_256() -> None:
    """G1: inclusion proofs verify for every leaf of every tree size 1 to 256."""
    all_leaves = leaves(256)
    checked = 0
    for n in range(1, 257):
        ls = all_leaves[:n]
        root = mth(ls)
        for i in range(n):
            p = inclusion_proof(i, ls)
            assert len(p) == proof_length(i, n)
            assert verify_inclusion(i, n, ls[i], p, root), (n, i)
            checked += 1
    assert checked == 256 * 257 // 2


def test_wrong_index_or_size_fails() -> None:
    ls = leaves(13)
    root = mth(ls)
    p = inclusion_proof(5, ls)
    assert not verify_inclusion(4, 13, ls[5], p, root)
    assert not verify_inclusion(13, 13, ls[5], p, root)
    assert not verify_inclusion(5, 13, ls[5], p[:-1], root)
    assert not verify_inclusion(5, 13, ls[5], [*p, ls[0]], root)


def test_inner_node_is_not_a_leaf() -> None:
    ls = leaves(4)
    root = mth(ls)
    inner = node_hash(ls[0], ls[1])
    assert not verify_inclusion(0, 4, inner, [node_hash(ls[2], ls[3])], root)


def test_root_from_proof_rejects_bad_index() -> None:
    with pytest.raises(MerkleError):
        root_from_proof(3, 3, leaves(1)[0], [])


def test_proof_index_out_of_range() -> None:
    with pytest.raises(MerkleError):
        inclusion_proof(3, leaves(3))
