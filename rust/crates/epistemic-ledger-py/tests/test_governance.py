"""Key governance and tenant partitions (DESIGN-15 stage 2, claim T1).

Exercises the _core bindings: enrollment windows enforced by
governed verification (before enrollment, after revocation,
never enrolled, governance by a key without authority), and the
cross-partition probe suite — every API path aimed at a second
partition from the first is refused or answers from the opened
partition alone.
"""

from __future__ import annotations

import json

import pytest

core = pytest.importorskip("epistemic_ledger._core")

from epistemic_ledger import anchors  # noqa: E402

GENESIS = "01" * 32
WRITER = "02" * 32
CHECKPOINT = "03" * 32
STRANGER = "09" * 32
T = "2026-10-30T00:00:00Z"


def _pubkey(seed_hex: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    return (
        key.public_key()
        .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        .hex()
    )


def _enroll(store, signer_seed, signer_actor, key_id, pubkey, role):
    store.append(
        T,
        signer_actor,
        "key_enrollment",
        json.dumps({"key_id": key_id, "pubkey": pubkey, "role": role}),
        signer_seed,
    )


def _governed_store(tmp_path):
    store = core.RustStore.open(str(tmp_path / "store"))
    _enroll(store, GENESIS, "genesis", "w1", _pubkey(WRITER), "writer")
    _enroll(store, GENESIS, "genesis", "ck1", _pubkey(CHECKPOINT), "checkpoint")
    store.append(T, "w1", "note", json.dumps({"i": 1}), WRITER)
    return store


def test_governed_store_verifies(tmp_path):
    store = _governed_store(tmp_path)
    assert store.verify_governed("genesis", _pubkey(GENESIS)) == 3
    report = json.loads(store.governance_json("genesis", _pubkey(GENESIS)))
    assert report["violations"] == []
    assert {w["key_id"] for w in report["windows"]} == {"w1", "ck1"}
    # The checkpoint key is effective after its enrollment seq,
    # not at it — the STH window reading verifier-side code uses.
    assert anchors.key_effective_at(report, "ck1", 3)
    assert not anchors.key_effective_at(report, "ck1", 2)
    assert not anchors.key_effective_at(report, "nobody", 3)


def test_record_before_enrollment_fails_governed_only(tmp_path):
    store = core.RustStore.open(str(tmp_path / "store"))
    store.append(T, "w1", "note", json.dumps({"i": 0}), WRITER)
    _enroll(store, GENESIS, "genesis", "w1", _pubkey(WRITER), "writer")
    store.append(T, "w1", "note", json.dumps({"i": 1}), WRITER)
    report = json.loads(store.governance_json("genesis", _pubkey(GENESIS)))
    assert len(report["violations"]) == 1
    assert "unenrolled key w1" in report["violations"][0]
    with pytest.raises(RuntimeError, match="governance violations"):
        store.verify_governed("genesis", _pubkey(GENESIS))
    # Governance is additive: the plain signature check still
    # passes — every signature here is genuine.
    assert store.verify(json.dumps({"w1": _pubkey(WRITER)}), 1) == 3


def test_record_after_revocation_fails(tmp_path):
    store = _governed_store(tmp_path)
    store.append(T, "genesis", "key_revocation", json.dumps({"key_id": "w1"}), GENESIS)
    store.append(T, "w1", "note", json.dumps({"i": 2}), WRITER)
    report = json.loads(store.governance_json("genesis", _pubkey(GENESIS)))
    assert any("key w1 revoked" in v for v in report["violations"])
    with pytest.raises(RuntimeError, match="governance violations"):
        store.verify_governed("genesis", _pubkey(GENESIS))


def test_unenrolled_signer_fails(tmp_path):
    store = _governed_store(tmp_path)
    store.append(T, "stranger", "note", json.dumps({"i": 9}), STRANGER)
    report = json.loads(store.governance_json("genesis", _pubkey(GENESIS)))
    assert any("unenrolled key stranger" in v for v in report["violations"])


def test_writer_cannot_enroll(tmp_path):
    store = core.RustStore.open(str(tmp_path / "store"))
    _enroll(store, GENESIS, "genesis", "w1", _pubkey(WRITER), "writer")
    # w1 holds the writer role: its enrollment of w2 is inert.
    _enroll(store, WRITER, "w1", "w2", _pubkey(STRANGER), "writer")
    store.append(T, "w2", "note", json.dumps({"i": 1}), STRANGER)
    report = json.loads(store.governance_json("genesis", _pubkey(GENESIS)))
    assert any("without governance authority" in v for v in report["violations"])
    assert any("unenrolled key w2" in v for v in report["violations"])
    assert {w["key_id"] for w in report["windows"]} == {"w1"}


def test_cross_partition_probe(tmp_path):
    root = str(tmp_path / "partitions")
    acme = core.RustStore.open_partition(root, "acme")
    acme.append(T, "w1", "note", json.dumps({"tenant": "acme", "i": 1}), WRITER)
    acme.append(T, "w1", "note", json.dumps({"tenant": "acme", "i": 2}), WRITER)
    globex = core.RustStore.open_partition(root, "globex")
    globex.append(T, "w1", "note", json.dumps({"tenant": "globex", "i": 1}), WRITER)

    acme_records = json.loads(
        core.read_records_json(core.tenant_partition_dir(root, "acme"))
    )
    globex_records = json.loads(
        core.read_records_json(core.tenant_partition_dir(root, "globex"))
    )
    assert [r["payload"]["i"] for r in acme_records] == [1, 2]
    assert [r["payload"]["tenant"] for r in globex_records] == ["globex"]

    # Escape spellings are refused by both entry points.
    for bad in ["..", "../globex", "acme/../globex", "", "ACME", "a/b"]:
        with pytest.raises(RuntimeError):
            core.RustStore.open_partition(root, bad)
        with pytest.raises(RuntimeError):
            core.tenant_partition_dir(root, bad)

    # A live partition refuses a second writer — the isolation is
    # physical, not a flag.
    with pytest.raises(RuntimeError):
        core.RustStore.open_partition(root, "acme")
