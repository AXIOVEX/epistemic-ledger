"""Snapshot/restore through the bindings (DESIGN-13 section 4).

This is the CI restore drill for claim R1: snapshot a store,
restore it somewhere else, and diff chain head, records, and
verification. Claim R2: one altered byte in the bundle fails
verification before restore begins, and restore writes nothing.
"""

import json
import os
import shutil

import pytest
from epistemic_ledger._core import (
    RustStore,
    read_records_json,
    restore_snapshot_json,
    snapshot_json,
    verify_snapshot_json,
)

SEED = "07" * 32


def _build_store(path, n=9, signed=False):
    store = RustStore.open(str(path))
    last = None
    for i in range(n):
        last = store.append(
            "2026-10-27T00:00:00Z",
            "system",
            "assert",
            json.dumps({"i": i}),
            SEED if signed else None,
        )
    head = store.head_hash
    count = store.verify("{}", 1)
    del store
    return head, count, last


def test_snapshot_restore_roundtrip(tmp_path):
    src = tmp_path / "src"
    head, count, _ = _build_store(src, signed=True)
    bundle = tmp_path / "bundle"
    report = json.loads(snapshot_json(str(src), str(bundle)))
    assert report["events"] == count
    assert report["head_hash"] == head
    assert json.loads(verify_snapshot_json(str(bundle))) == report

    dst = tmp_path / "dst"
    assert json.loads(restore_snapshot_json(str(bundle), str(dst))) == report
    # Indistinguishable from the original: same records, byte for
    # byte, and the same verification count.
    assert read_records_json(str(dst)) == read_records_json(str(src))
    store = RustStore.open(str(dst))
    assert store.head_hash == head
    assert store.verify("{}", 1) == count
    del store


def test_one_altered_byte_fails_verification_and_blocks_restore(tmp_path):
    src = tmp_path / "src"
    _build_store(src, n=4)
    bundle = tmp_path / "bundle"
    snapshot_json(str(src), str(bundle))

    log = bundle / "events.log"
    data = bytearray(log.read_bytes())
    data[len(data) // 2] ^= 0x01
    log.write_bytes(bytes(data))
    with pytest.raises(RuntimeError):
        verify_snapshot_json(str(bundle))
    dst = tmp_path / "dst"
    with pytest.raises(RuntimeError):
        restore_snapshot_json(str(bundle), str(dst))
    assert not (dst / "events.log").exists()


def test_restore_drill_on_a_migrated_store(tmp_path):
    """The R1 drill on realistic content: a 0.12 store, migrated
    to the chained format, snapshotted, the original deleted, and
    the restore diffed against the original — chain head, record
    stream, and every live score re-derived from the records."""
    from epistemic_ledger import Ledger
    from epistemic_ledger.migrate import migrate_store

    legacy_dir = tmp_path / "legacy"
    led = Ledger(str(legacy_dir))
    a = led.assert_claim("alpha", 0.9)
    b = led.assert_claim("beta", 0.4)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    led.ingest_evidence("new fact", 0.8)
    live_scores = led._all_live_scores()
    led.close()

    chained = tmp_path / "chained"
    mig = migrate_store(str(legacy_dir), str(chained))
    bundle = tmp_path / "bundle"
    report = json.loads(snapshot_json(str(chained), str(bundle)))
    assert report["head_hash"] == mig["head_hash"]
    source_records = read_records_json(str(chained))

    shutil.rmtree(chained)  # the original is gone; the bundle is all we have
    restored = tmp_path / "restored"
    restore_snapshot_json(str(bundle), str(restored))
    assert read_records_json(str(restored)) == source_records

    records = json.loads(read_records_json(str(restored)))
    # Re-derive terminal scores from the restored record stream
    # (the verify_store rule: last score_revision wins, else the
    # assert prior) and compare with the original live scores.
    terminal = {}
    for rec in records:
        payload = rec["payload"]
        if rec["type"] == "assert" and "claim_id" in payload:
            terminal[payload["claim_id"]] = payload["prior"]
        elif rec["type"] == "score_revision":
            terminal[payload["claim_id"]] = payload["new_score"]
    assert terminal == live_scores
    store = RustStore.open(str(restored))
    assert store.head_hash == mig["head_hash"]
    assert store.verify("{}", mig["signed_from_seq"]) == mig["total_records"]
    del store
    assert os.path.exists(restored / "events.log")
