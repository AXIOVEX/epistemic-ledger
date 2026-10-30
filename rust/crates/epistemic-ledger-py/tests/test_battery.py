"""The adversarial battery (DESIGN-13 section 7).

Drills, not examples: history attacks, crash attacks, corruption
with and without a snapshot to repair from, concurrency, and
adversarial graph shapes for impact. Every drill ends with a
health check and a full verification, and the battery fails if
either reports clean over damage (claim E4).
"""

import json
import os
import subprocess
import sys
import time

import pytest

from epistemic_ledger import Ledger, anchors
from epistemic_ledger._core import (
    RustStore,
    read_records_json,
    restore_snapshot_json,
    snapshot_json,
    sth_fork_json,
    verify_consistency_json,
    verify_inclusion_json,
    verify_sth_json,
)

SEED = "07" * 32
ATTACKER_SEED = "09" * 32
T0 = "2026-01-01T00:00:00+00:00"


def _pubkey_hex(seed_hex):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )

    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


PUBKEYS = json.dumps({"w": _pubkey_hex(SEED)})


def _signed_store(path, n=24):
    store = RustStore.open(str(path))
    for i in range(n):
        store.append(T0, "w", "note", json.dumps({"i": i}), SEED)
    return store


def _log_bytes(path):
    with open(os.path.join(str(path), "events.log"), "rb") as f:
        return f.read()


def _write_log(path, raw):
    os.makedirs(str(path), exist_ok=True)
    with open(os.path.join(str(path), "events.log"), "wb") as f:
        f.write(raw)


# CRC-32C (Castagnoli), table-driven — the chain format's line
# checksum. Python's binascii.crc32 is the ISO polynomial, not
# Castagnoli, so the battery carries its own.
_CRC_TABLE = []
for _i in range(256):
    _c = _i
    for _ in range(8):
        _c = (_c >> 1) ^ (0x82F63B78 if _c & 1 else 0)
    _CRC_TABLE.append(_c)


def _crc32c(data):
    crc = 0xFFFFFFFF
    for b in data:
        crc = _CRC_TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


# ------------------------------------------------------------------
# History attacks
# ------------------------------------------------------------------


def test_rewrite_with_recomputed_hashes_fails_on_signatures(tmp_path):
    """The attacker rebuilds the whole chain with correct hashes
    but cannot sign as the writer: verification must fail."""
    src = _signed_store(tmp_path / "victim", n=12)
    records = json.loads(read_records_json(str(tmp_path / "victim")))
    src.verify(PUBKEYS, 1)
    forged = RustStore.open(str(tmp_path / "forged"))
    for rec in records:
        payload = dict(rec["payload"])
        if rec["seq"] == 5:
            payload["i"] = 999  # the lie the rewrite exists to plant
        forged.append(
            rec["t"], rec["actor"], rec["type"], json.dumps(payload), ATTACKER_SEED
        )
    # Structurally the forged chain is perfect...
    assert forged.verify("{}", 1) == 12
    # ...and it fails the moment signatures are checked.
    with pytest.raises(RuntimeError):
        forged.verify(PUBKEYS, 1)


def test_copied_signatures_over_altered_payload_fail(tmp_path):
    """Keep the original hash and signature, change the payload:
    the hash no longer commits to the content. The line still
    parses and links (open is the fast structural pass), and the
    deep verification catches it at the exact sequence number."""
    src_dir = tmp_path / "victim"
    _signed_store(src_dir, n=12)
    lines = _log_bytes(src_dir).split(b"\n")
    # Line index 4 is seq 5 (plus the trailing empty split piece).
    crc_hex, _, body = lines[4].partition(b" ")
    rec = json.loads(body)
    rec["payload"]["i"] = 999
    new_body = json.dumps(rec, separators=(",", ":")).encode()
    lines[4] = f"{_crc32c(new_body):08x}".encode() + b" " + new_body
    broken = tmp_path / "broken"
    _write_log(broken, b"\n".join(lines))
    store = RustStore.open(str(broken))
    with pytest.raises(RuntimeError) as exc_info:
        store.verify(PUBKEYS, 1)
    assert "seq 5" in str(exc_info.value)


# ------------------------------------------------------------------
# Crash attacks
# ------------------------------------------------------------------


def test_kill_during_append_burst_recovers(tmp_path):
    """SIGKILL a writer mid-burst: the store reopens, the torn
    tail (if any) is recovered, and what survives verifies."""
    target = str(tmp_path / "victim")
    script = (
        "import json, sys\n"
        "from epistemic_ledger._core import RustStore\n"
        f"s = RustStore.open({target!r})\n"
        "for i in range(100000):\n"
        f"    s.append({T0!r}, 'w', 'note', json.dumps({{'i': i}}), {SEED!r})\n"
        "    print(i, flush=True)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    seen = 0
    while seen < 40:
        line = proc.stdout.readline()
        if not line:
            break
        seen += 1
    proc.kill()
    proc.wait(timeout=10)
    store = RustStore.open(target)  # recovery happens here
    count = store.verify(PUBKEYS, 1)
    assert count >= 40
    report = json.loads(store.open_report_json())
    assert report["events"] == count


def test_torn_final_write_at_every_byte_offset(tmp_path):
    """Truncate the log at every offset inside the final record:
    each time, open recovers to the last complete record and the
    surviving chain verifies."""
    src_dir = tmp_path / "victim"
    store = _signed_store(src_dir, n=6)
    head_before = store.head_hash
    raw = _log_bytes(src_dir)
    last_line_start = raw.rfind(b"\n", 0, len(raw) - 1) + 1
    last_line = raw[last_line_start:]
    body_len = len(last_line) - (1 if last_line.endswith(b"\n") else 0)
    for cut in range(last_line_start, len(raw)):
        d = tmp_path / f"torn-{cut}"
        _write_log(d, raw[:cut])
        reopened = RustStore.open(str(d))
        report = json.loads(reopened.open_report_json())
        if cut - last_line_start >= body_len:
            # Only the terminating newline was lost: the record's
            # bytes are all present, so it stands (6 events).
            assert report["events"] == 6, f"cut at {cut}"
            assert reopened.verify(PUBKEYS, 1) == 6
        else:
            assert report["events"] == 5, f"cut at {cut}"
            assert reopened.verify(PUBKEYS, 1) == 5


def test_projection_deleted_rebuilds_identically(tmp_path):
    """The Python store's projection is a fold of the log: delete
    it, rebuild from the log alone, and every score is reproduced
    (Ledger.rebuild_projection, the documented recovery path)."""
    path = str(tmp_path / "store")
    led = Ledger(path)
    a = led.assert_claim("alpha", 0.9)
    b = led.assert_claim("beta", 0.4)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    led.manual_score(a, 0.7)
    before = {cid: led.get_score(cid) for cid in (a, b)}
    led.close()
    os.remove(os.path.join(path, "ledger.db"))
    report = Ledger.rebuild_projection(path)
    assert report["ok"] is True
    led = Ledger(path)
    assert {cid: led.get_score(cid) for cid in (a, b)} == before
    assert led.health()["ok"] is True
    led.close()


def test_projection_corruption_is_never_clean(tmp_path):
    """Corrupt the projection two ways — a tampered score written
    straight into the database, and raw byte damage — and
    verification must catch both (or the open must refuse):
    health never reports clean over damage. Since DESIGN-16 S1c a
    recovering open also repairs drift from the log and reports it
    on open_report — caught and repaired, never silently clean.
    The rebuild then restores the exact state."""
    import sqlite3

    path = str(tmp_path / "store")
    led = Ledger(path)
    a = led.assert_claim("alpha", 0.9)
    led.close()
    db = os.path.join(path, "ledger.db")

    # (a) Data-level tampering: the projection disagrees with the log.
    conn = sqlite3.connect(db)
    conn.execute("UPDATE claims SET score = 0.123 WHERE claim_id = ?", (a,))
    conn.commit()
    conn.close()
    led = Ledger(path, recover=False)
    assert led.verify_store()["ok"] is False
    assert led.health()["ok"] is False
    led.close()
    # A recovering open catches the same drift and repairs it from
    # the log, reporting the repair — never silently clean (S1c).
    led = Ledger(path)
    assert led.open_report["rebuilt"] is True
    assert led.verify_store()["ok"] is True
    led.close()

    # (b) Byte-level damage across the header page. (Offset zero,
    # not the middle: mid-file damage can land in a free page that
    # no logical read ever touches — undetectable by construction,
    # and this drill used to pass there only because part (a)'s
    # drift was still present. Header damage is deterministic:
    # the file stops being a database at all.)
    with open(db, "r+b") as f:
        f.seek(0)
        f.write(b"\xff" * 256)
    caught = False
    try:
        led = Ledger(path)
        caught = not led.verify_store()["ok"] or not led.health()["ok"]
        led.close()
    except Exception:
        caught = True  # a refused open is also a catch
    assert caught

    # Caught by verification, then rebuilt from the log (section 7).
    Ledger.rebuild_projection(path)
    led = Ledger(path)
    assert led.get_score(a) == 0.9
    assert led.health()["ok"] is True
    led.close()


# ------------------------------------------------------------------
# Corruption drills: with and without a snapshot (E3, E4)
# ------------------------------------------------------------------


def test_snapshot_repairs_corrupted_store(tmp_path):
    src_dir = tmp_path / "victim"
    store = _signed_store(src_dir, n=30)
    original = read_records_json(str(src_dir))
    bundle = tmp_path / "bundle"
    snapshot_json(str(src_dir), str(bundle))
    del store  # release the writer lock before reopening
    # Damage the live store mid-history.
    lines = _log_bytes(src_dir).split(b"\n")
    crc_hex, _, body = lines[10].partition(b" ")
    rec = json.loads(body)
    rec["payload"]["i"] = 31337
    new_body = json.dumps(rec, separators=(",", ":")).encode()
    lines[10] = f"{_crc32c(new_body):08x}".encode() + b" " + new_body
    _write_log(src_dir, b"\n".join(lines))
    damaged = RustStore.open(str(src_dir))
    with pytest.raises(RuntimeError):
        damaged.verify(PUBKEYS, 1)  # the damage is caught, not passed over
    del damaged
    restored = tmp_path / "restored"
    report = json.loads(restore_snapshot_json(str(bundle), str(restored)))
    assert report["events"] == 30
    assert read_records_json(str(restored)) == original
    store = RustStore.open(str(restored))
    assert store.verify(PUBKEYS, 1) == 30


def test_corruption_without_snapshot_stops_at_first_bad_record(tmp_path):
    src_dir = tmp_path / "victim"
    _signed_store(src_dir, n=20)
    lines = _log_bytes(src_dir).split(b"\n")
    crc_hex, _, body = lines[7].partition(b" ")  # seq 8
    rec = json.loads(body)
    rec["payload"]["i"] = 8888
    new_body = json.dumps(rec, separators=(",", ":")).encode()
    lines[7] = f"{_crc32c(new_body):08x}".encode() + b" " + new_body
    _write_log(src_dir, b"\n".join(lines))
    store = RustStore.open(str(src_dir))
    with pytest.raises(RuntimeError) as exc_info:
        store.verify(PUBKEYS, 1)
    # The loss is reported exactly: the first bad sequence number.
    assert "seq 8" in str(exc_info.value)


# ------------------------------------------------------------------
# Concurrency
# ------------------------------------------------------------------


def test_second_writer_is_refused(tmp_path):
    first = _signed_store(tmp_path / "store", n=3)
    with pytest.raises(RuntimeError):
        RustStore.open(str(tmp_path / "store"))
    assert first.verify(PUBKEYS, 1) == 3


def test_readers_observe_only_complete_records(tmp_path):
    target = str(tmp_path / "store")
    script = (
        "import json, time\n"
        "from epistemic_ledger._core import RustStore\n"
        f"s = RustStore.open({target!r})\n"
        "for i in range(150):\n"
        f"    s.append({T0!r}, 'w', 'note', json.dumps({{'i': i}}), {SEED!r})\n"
        "    time.sleep(0.004)\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    reads = 0
    while proc.poll() is None:
        records = json.loads(read_records_json(target))
        seqs = [r["seq"] for r in records]
        assert seqs == list(range(1, len(seqs) + 1))
        reads += 1
        time.sleep(0.01)
    proc.wait(timeout=10)
    assert reads >= 3
    assert len(json.loads(read_records_json(target))) == 150


# ------------------------------------------------------------------
# Impact on adversarial graph shapes
# ------------------------------------------------------------------


def _graph_store(tmp_path):
    return Ledger(str(tmp_path / "graph"))


def test_impact_deep_chain(tmp_path):
    led = _graph_store(tmp_path)
    ids = [led.assert_claim(f"d{i}", 0.5) for i in range(800)]
    for i in range(1, 800):
        led.add_support(ids[i], ids[i - 1], "deductive", p_given=1.0, p_given_not=0.0)
    result = led.impact(ids[0])
    assert len(result["nodes"]) == 799
    tail = next(d for d in result["nodes"] if d["id"] == ids[-1])
    assert tail["distance"] == 799
    led.close()


def test_impact_wide_fan(tmp_path):
    led = _graph_store(tmp_path)
    root = led.assert_claim("root", 0.5)
    for i in range(1200):
        leaf = led.assert_claim(f"leaf{i}", 0.5)
        led.add_support(leaf, root, "evidential", p_given=0.9, p_given_not=0.1)
    result = led.impact(root, max_results=2000)
    assert len(result["nodes"]) == 1200
    assert all(d["distance"] == 1 for d in result["nodes"])
    led.close()


def test_impact_near_cycle_terminates(tmp_path):
    led = _graph_store(tmp_path)
    ids = [led.assert_claim(f"r{i}", 0.5) for i in range(300)]
    for i in range(300):
        led.add_support(
            ids[(i + 1) % 300], ids[i], "deductive", p_given=1.0, p_given_not=0.0
        )
    result = led.impact(ids[0])
    assert len(result["nodes"]) == 299  # everyone but itself
    led.close()


# ------------------------------------------------------------------
# Anchoring attacks (DESIGN-15 stage 1, claims A1-A3)
# ------------------------------------------------------------------

CK_PUB = _pubkey_hex(SEED)


def test_anchored_history_rewrite_is_detected(tmp_path):
    """A1: pin STHs over three checkpoints; a rewritten history
    below the anchor — same shape, one payload changed in the
    first segment, its own later STH signed with the same
    checkpoint key — fails consistency against the pinned head.
    A byte-level rewrite of the original log is refused at open."""
    store = _signed_store(tmp_path / "anchored", n=3072)
    sth1 = store.sth_json(T0, "ck-1", SEED, 1)
    sth3 = store.sth_json(T0, "ck-1", SEED, 3)
    proof = store.consistency_proof_json(1, 3)
    assert verify_consistency_json(sth1, sth3, proof) is True
    assert anchors.verify_consistency(
        json.loads(sth1), json.loads(sth3), json.loads(proof)
    )

    rewritten = RustStore.open(str(tmp_path / "rewritten"))
    for i in range(3072):
        payload = {"i": 999 if i == 4 else i}
        rewritten.append(T0, "w", "note", json.dumps(payload), SEED)
    bad3 = rewritten.sth_json(T0, "ck-1", SEED, 3)
    bad_proof = rewritten.consistency_proof_json(1, 3)
    # The rewritten history is internally consistent...
    assert verify_consistency_json(
        rewritten.sth_json(T0, "ck-1", SEED, 1), bad3, bad_proof
    )
    # ...and detected the moment it is checked against the anchor.
    assert verify_consistency_json(sth1, bad3, bad_proof) is False
    assert not anchors.verify_consistency(
        json.loads(sth1), json.loads(bad3), json.loads(bad_proof)
    )
    del rewritten

    raw = bytearray(_log_bytes(tmp_path / "anchored"))
    line5_end = raw.find(
        b"\n", raw.find(b"\n", raw.find(b"\n", raw.find(b"\n")) + 1) + 1
    )
    raw[line5_end - 5] ^= 0xFF
    del store
    _write_log(tmp_path / "anchored", bytes(raw))
    with pytest.raises(RuntimeError):
        RustStore.open(str(tmp_path / "anchored"))


def test_inclusion_proof_verifies_standalone(tmp_path):
    """A2: the pure-Python verifier, given only a record's hash,
    its inclusion proof, the STH, and the checkpoint public key,
    accepts the real record and rejects a mutated record, the
    wrong record, and the wrong checkpoint."""
    store = _signed_store(tmp_path / "incl", n=2048)
    sth2 = json.loads(store.sth_json(T0, "ck-1", SEED, 2))
    sth1 = json.loads(store.sth_json(T0, "ck-1", SEED, 1))
    proof = json.loads(store.inclusion_proof_json(1500))
    records = json.loads(read_records_json(str(tmp_path / "incl")))
    leaf = records[1499]["hash"]
    assert proof["leaf_hash"] == leaf
    assert verify_inclusion_json(
        leaf,
        proof["index"],
        proof["segment_len"],
        json.dumps(proof["proof"]),
        proof["root"],
    )
    assert anchors.verify_anchored_record(leaf, proof, sth2, CK_PUB)
    # Mutated record.
    mutated = ("0" if leaf[0] != "0" else "1") + leaf[1:]
    assert not anchors.verify_anchored_record(mutated, proof, sth2, CK_PUB)
    # Wrong record: the next record's hash against this proof.
    assert not anchors.verify_anchored_record(
        records[1500]["hash"], proof, sth2, CK_PUB
    )
    # Wrong checkpoint: checkpoint 1's head over a checkpoint 2 proof.
    assert not anchors.verify_anchored_record(leaf, proof, sth1, CK_PUB)
    del store


def test_two_signed_heads_same_size_is_a_fork(tmp_path):
    """A3: two stores of identical shape with different histories
    produce two validly signed STHs for checkpoint 1 at the same
    tree size with different roots. Both signatures verify — that
    is what makes it equivocation, and the fork test must fire."""
    a = _signed_store(tmp_path / "fa", n=1024)
    b = RustStore.open(str(tmp_path / "fb"))
    for i in range(1024):
        b.append(T0, "w", "note", json.dumps({"i": i, "side": "b"}), SEED)
    sth_a = a.sth_json(T0, "ck-1", SEED, 1)
    sth_b = b.sth_json(T0, "ck-1", SEED, 1)
    assert verify_sth_json(sth_a, CK_PUB) and verify_sth_json(sth_b, CK_PUB)
    assert anchors.verify_sth(json.loads(sth_a), CK_PUB)
    assert anchors.verify_sth(json.loads(sth_b), CK_PUB)
    assert json.loads(sth_a)["tree_size"] == json.loads(sth_b)["tree_size"]
    assert sth_fork_json(sth_a, sth_b) is True
    assert anchors.is_fork(json.loads(sth_a), json.loads(sth_b))
    assert sth_fork_json(sth_a, sth_a) is False
    assert not anchors.is_fork(json.loads(sth_a), json.loads(sth_a))
    del a, b
