"""Signed tree heads and checkpoint proofs (DESIGN-15 stage 1).

Exercises the _core bindings: STH issuance and standalone
verification, inclusion proofs verified with no store access, and
consistency proofs between checkpoints. The adversarial drills for
claims A1-A3 live in the battery; this file pins the API contract.
"""

from __future__ import annotations

import json

import pytest

core = pytest.importorskip("epistemic_ledger._core")

SEED = "07" * 32
OTHER_SEED = "08" * 32


def _pubkey(seed_hex: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _fill(store, count: int, start: int = 0) -> None:
    for i in range(start, start + count):
        store.append(
            "2026-01-01T00:00:00Z",
            "anchor-writer",
            "stress_record",
            json.dumps({"i": i}),
            SEED,
        )


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("sth") / "store")
    s = core.RustStore.open(path)
    _fill(s, 1024 * 3)
    return s


def test_sth_signs_and_verifies_standalone(store):
    sth = store.sth_json("2026-10-30T00:00:00Z", "ck-1", SEED)
    parsed = json.loads(sth)
    assert parsed["tree_size"] == 3072
    assert parsed["checkpoint_seq"] == 3
    assert core.verify_sth_json(sth, _pubkey(SEED)) is True
    assert core.verify_sth_json(sth, _pubkey(OTHER_SEED)) is False


def test_sth_for_earlier_checkpoint(store):
    sth = json.loads(store.sth_json("2026-10-30T00:00:00Z", "ck-1", SEED, 1))
    assert sth["tree_size"] == 1024
    assert sth["checkpoint_seq"] == 1


def test_sth_tamper_rejected(store):
    sth = json.loads(store.sth_json("2026-10-30T00:00:00Z", "ck-1", SEED))
    sth["root"] = "00" * 32
    assert core.verify_sth_json(json.dumps(sth), _pubkey(SEED)) is False


def test_inclusion_proof_verifies_without_store(store):
    proof = json.loads(store.inclusion_proof_json(1500))
    assert proof["checkpoint_seq"] == 2
    assert core.verify_inclusion_json(
        proof["leaf_hash"],
        proof["index"],
        proof["segment_len"],
        json.dumps(proof["proof"]),
        proof["root"],
    ) is True
    # A proof for one record does not verify for another's leaf.
    assert core.verify_inclusion_json(
        "00" * 32,
        proof["index"],
        proof["segment_len"],
        json.dumps(proof["proof"]),
        proof["root"],
    ) is False


def test_inclusion_requires_checkpoint(store, tmp_path):
    small = core.RustStore.open(str(tmp_path / "small"))
    _fill(small, 10)
    with pytest.raises(Exception):
        small.inclusion_proof_json(5)


def test_consistency_between_checkpoints(store):
    first = store.sth_json("2026-10-30T00:00:00Z", "ck-1", SEED, 1)
    third = store.sth_json("2026-10-30T01:00:00Z", "ck-1", SEED, 3)
    proof = store.consistency_proof_json(1, 3)
    assert core.verify_consistency_json(first, third, proof) is True
    # Reversed heads do not verify.
    assert core.verify_consistency_json(third, first, proof) is False


def test_fork_detection(store):
    first = json.loads(store.sth_json("2026-10-30T00:00:00Z", "ck-1", SEED, 1))
    forked = dict(first)
    forked["root"] = "00" * 32
    assert core.sth_fork_json(json.dumps(first), json.dumps(forked)) is True
    assert core.sth_fork_json(json.dumps(first), json.dumps(first)) is False
