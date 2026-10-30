"""Unit tests for the standalone anchor verifier (DESIGN-15
stage 1). Synthetic artifacts only — no store, no Rust extension:
STHs are signed here with the package's vendored Ed25519, and the
Merkle helpers mirror the checkpoint format so inclusion proofs
can be built in the test. Agreement with the Rust core's artifacts
is the battery drills' job; this file pins the verifier's own
accept/reject behavior on every path."""

from __future__ import annotations

import hashlib
import json

from epistemic_ledger import anchors, ed25519

SEED = bytes.fromhex("07" * 32)
OTHER_SEED = bytes.fromhex("08" * 32)
PUB = ed25519.publickey(SEED).hex()
TS = "2026-10-30T00:00:00Z"


def _digest(sth: dict) -> bytes:
    unsigned = {
        "checkpoint_seq": sth["checkpoint_seq"],
        "key_id": sth["key_id"],
        "root": sth["root"],
        "timestamp": sth["timestamp"],
        "tree_size": sth["tree_size"],
    }
    canonical = json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(b"ELSTH1" + canonical).digest()


def _sth(root: str, checkpoint_seq: int, tree_size: int, seed: bytes = SEED) -> dict:
    sth = {
        "tree_size": tree_size,
        "root": root,
        "checkpoint_seq": checkpoint_seq,
        "timestamp": TS,
        "key_id": "ck-1",
    }
    sth["signature"] = ed25519.sign(seed, _digest(sth)).hex()
    return sth


def _lh(h: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + h).digest()


def _nh(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def _root(leaves: list[bytes]) -> bytes:
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return _lh(leaves[0])
    k = _split(len(leaves))
    return _nh(_root(leaves[:k]), _root(leaves[k:]))


def _proof(leaves: list[bytes], index: int) -> list[bytes]:
    if len(leaves) == 1:
        return []
    k = _split(len(leaves))
    if index < k:
        return _proof(leaves[:k], index) + [_root(leaves[k:])]
    return _proof(leaves[k:], index - k) + [_root(leaves[:k])]


def _segment(n: int, tag: str) -> list[bytes]:
    return [hashlib.sha256(f"{tag}-{i}".encode()).digest() for i in range(n)]


def _checkpoints() -> tuple[list[dict], list[bytes]]:
    """Three checkpoints of four records each, chain-linked."""
    cps = []
    prev = _root([]).hex()
    for s in range(3):
        leaves = _segment(4, f"seg{s}")
        root = _root(leaves).hex()
        cps.append(
            {
                "first_seq": s * 4 + 1,
                "last_seq": s * 4 + 4,
                "root": root,
                "prev_root": prev,
            }
        )
        prev = root
    return cps, _segment(4, "seg1")


def test_sth_accepts_and_rejects():
    sth = _sth("ab" * 32, 1, 4)
    assert anchors.verify_sth(sth, PUB)
    assert not anchors.verify_sth(sth, ed25519.publickey(OTHER_SEED).hex())
    tampered = dict(sth, root="00" * 32)
    assert not anchors.verify_sth(tampered, PUB)
    assert not anchors.verify_sth(dict(sth, signature="zz"), PUB)
    assert not anchors.verify_sth({"root": "ab" * 32}, PUB)


def test_fork_detection():
    a = _sth("ab" * 32, 1, 4)
    b = _sth("cd" * 32, 1, 4)
    assert anchors.is_fork(a, b)
    assert not anchors.is_fork(a, a)
    later = _sth("cd" * 32, 2, 8)
    assert not anchors.is_fork(a, later)


def test_inclusion_accepts_and_rejects():
    leaves = _segment(8, "inc")
    root = _root(leaves).hex()
    for index in (0, 3, 7):
        proof = [h.hex() for h in _proof(leaves, index)]
        assert anchors.verify_inclusion(leaves[index].hex(), index, 8, proof, root)
        assert not anchors.verify_inclusion(
            leaves[index].hex(), index, 8, proof, "00" * 32
        )
        assert not anchors.verify_inclusion(
            leaves[index].hex(), index, 8, proof[:-1], root
        )
        assert not anchors.verify_inclusion(
            leaves[(index + 1) % 8].hex(), index, 8, proof, root
        )
    assert not anchors.verify_inclusion(leaves[0].hex(), 0, 0, [], root)
    assert not anchors.verify_inclusion(leaves[0].hex(), 8, 8, [], root)
    assert not anchors.verify_inclusion("zz", 0, 8, [], root)


def test_consistency_accepts_and_rejects():
    cps, _ = _checkpoints()
    first = _sth(cps[0]["root"], 1, 4)
    third = _sth(cps[2]["root"], 3, 12)
    proof = {"checkpoints": cps[1:]}
    assert anchors.verify_consistency(first, third, proof)
    assert anchors.verify_consistency(first, first, {"checkpoints": []})
    # Reversed heads, a skipped link, a broken link, a wrong end.
    assert not anchors.verify_consistency(third, first, proof)
    assert not anchors.verify_consistency(first, third, {"checkpoints": cps[2:]})
    broken = {"checkpoints": [dict(cps[1], prev_root="00" * 32), cps[2]]}
    assert not anchors.verify_consistency(first, third, broken)
    wrong_end = _sth("00" * 32, 3, 12)
    assert not anchors.verify_consistency(first, wrong_end, proof)


def test_anchored_record_composition():
    cps, seg1 = _checkpoints()
    index = 2
    leaf = seg1[index]
    inclusion = {
        "seq": cps[1]["first_seq"] + index,
        "checkpoint_seq": 2,
        "segment_first_seq": cps[1]["first_seq"],
        "segment_last_seq": cps[1]["last_seq"],
        "segment_len": len(seg1),
        "index": index,
        "leaf_hash": leaf.hex(),
        "proof": [h.hex() for h in _proof(seg1, index)],
        "root": cps[1]["root"],
    }
    sth = _sth(cps[1]["root"], 2, cps[1]["last_seq"])
    assert anchors.verify_anchored_record(leaf.hex(), inclusion, sth, PUB)
    mutated = ("0" if leaf.hex()[0] != "0" else "1") + leaf.hex()[1:]
    assert not anchors.verify_anchored_record(mutated, inclusion, sth, PUB)
    wrong_cp = _sth(cps[0]["root"], 1, cps[0]["last_seq"])
    assert not anchors.verify_anchored_record(leaf.hex(), inclusion, wrong_cp, PUB)
    outside = dict(inclusion, seq=cps[1]["last_seq"] + 5)
    assert not anchors.verify_anchored_record(leaf.hex(), outside, sth, PUB)
