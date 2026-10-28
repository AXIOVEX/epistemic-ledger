"""Bindings tests: the Python face of the Rust core store."""

import json

import pytest

from epistemic_ledger._core import RustStore, health_json

SEED = "07" * 32


def _pubkey_hex(seed_hex):
    # Derive the Ed25519 public key with the package's vendored
    # implementation-free path: use the bindings themselves by
    # signing once and checking verify passes with the key the
    # Rust side derives. For the pubkey value we use the standard
    # library-free trick: nacl is not available, so compute via
    # the `cryptography` package if present, else skip.
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        pytest.skip("cryptography not available for pubkey derivation")
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    raw = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return raw.hex()


def test_append_verify_roundtrip(tmp_path):
    store = RustStore.open(str(tmp_path))
    rec = json.loads(store.append(
        "2026-10-27T00:00:00Z", "system", "assert",
        json.dumps({"claim_id": "C-1", "prior": 0.5}),
    ))
    assert rec["seq"] == 1
    assert rec["prev_hash"] == "0" * 64
    assert len(rec["hash"]) == 64
    assert store.next_seq == 2
    assert store.head_hash == rec["hash"]
    assert store.verify("{}") == 1
    report = json.loads(store.open_report_json())
    assert report["events"] == 1
    assert report["recovered_torn_bytes"] == 0


def test_signed_appends_verify_against_pubkey(tmp_path):
    pub = _pubkey_hex(SEED)
    store = RustStore.open(str(tmp_path))
    store.append("2026-10-27T00:00:00Z", "system", "assert",
                 json.dumps({"a": 1}))
    rec = json.loads(store.append(
        "2026-10-27T00:01:00Z", "wire-desk", "support",
        json.dumps({"b": 2}), SEED,
    ))
    assert rec["sig"] and len(rec["sig"]) == 128
    assert store.verify(json.dumps({"wire-desk": pub})) == 2
    # a wrong pubkey for the writer must fail
    with pytest.raises(RuntimeError):
        store.verify(json.dumps({"wire-desk": "09" * 32}))


def test_health_json(tmp_path):
    store = RustStore.open(str(tmp_path))
    for i in range(3):
        store.append("2026-10-27T00:00:00Z", "system", "assert",
                     json.dumps({"a": i}))
    del store
    health = json.loads(health_json(str(tmp_path), 2))
    assert health["events"] == 3
    assert health["lock_held"] is False
    assert len(health["checkpoints"]) == 1
    assert health["events_since_checkpoint"] == 1
