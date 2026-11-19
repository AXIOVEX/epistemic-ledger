"""Coverage tests for the auxiliary modules: anchors,
_verified, ed25519, prov, partitions, and pattern.

Each test exercises a real code path that the module's own
test file leaves unreached — error paths, malformed inputs,
boundary values, and failure handling (including filesystem
failures the code is written to survive). Synthetic inputs
only; no store and no Rust extension are required.
"""

from __future__ import annotations

import json
import os
import sys
import types

import pytest

from epistemic_ledger import _verified, anchors, ed25519, partitions, pattern, prov

# ------------------------------------------------------------------
# anchors: verify_anchored_record rejects before the inclusion
# check when the signed tree head itself does not verify.
# ------------------------------------------------------------------


def test_anchored_record_rejects_unverifiable_sth():
    sth = {
        "checkpoint_seq": 1,
        "key_id": "ck-1",
        "root": "ab" * 32,
        "timestamp": "2026-10-30T00:00:00Z",
        "tree_size": 4,
        "signature": "zz",  # not hex: verify_sth refuses it
    }
    inclusion = {
        "root": "ab" * 32,
        "checkpoint_seq": 1,
        "segment_first_seq": 1,
        "segment_last_seq": 4,
        "seq": 2,
        "index": 0,
        "segment_len": 4,
        "proof": [],
    }
    assert not anchors.verify_anchored_record("cd" * 32, inclusion, sth, "ef" * 32)
    # A head with no signature at all is refused the same way.
    unsigned = {k: v for k, v in sth.items() if k != "signature"}
    assert not anchors.verify_anchored_record("cd" * 32, inclusion, unsigned, "ef" * 32)


# ------------------------------------------------------------------
# anchors: key_effective_at walks every window shape.
# ------------------------------------------------------------------


def test_key_effective_at_skips_other_keys_and_dead_windows():
    report = {
        "windows": [
            # A different key's window: skipped entirely.
            {"key_id": "other", "enrolled_seq": 0, "revoked_seq": None},
            # This key, but not yet enrolled at the seq asked about.
            {"key_id": "ck-1", "enrolled_seq": 50, "revoked_seq": None},
            # This key, but already revoked by then.
            {"key_id": "ck-1", "enrolled_seq": 0, "revoked_seq": 10},
        ]
    }
    assert not anchors.key_effective_at(report, "ck-1", 20)
    # The revoked window was effective while it lasted.
    assert anchors.key_effective_at(report, "ck-1", 5)
    # The late window takes effect after its enrollment.
    assert anchors.key_effective_at(report, "ck-1", 60)


def test_key_effective_at_open_window_and_empty_report():
    report = {"windows": [{"key_id": "k", "enrolled_seq": 3, "revoked_seq": None}]}
    assert anchors.key_effective_at(report, "k", 4)
    assert not anchors.key_effective_at(report, "k", 3)  # enrollment is exclusive
    assert not anchors.key_effective_at({}, "k", 10)
    assert not anchors.key_effective_at({"windows": []}, "k", 10)


# ------------------------------------------------------------------
# _verified: failure handling inside the helpers.
# ------------------------------------------------------------------


def test_write_temp_reraises_when_cleanup_also_fails(tmp_path, monkeypatch):
    def bad_fdopen(fd, mode):
        raise OSError("injected write failure")

    def bad_unlink(path):
        raise OSError("injected unlink failure")

    monkeypatch.setattr(os, "fdopen", bad_fdopen)
    monkeypatch.setattr(os, "unlink", bad_unlink)
    with pytest.raises(OSError, match="injected write failure"):
        _verified._write_temp(str(tmp_path), b"data")


def test_fsync_dir_is_a_noop_on_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    # Returns without opening the directory (which Windows forbids).
    assert _verified._fsync_dir(str(tmp_path)) is None


def test_attempt_swallows_unlink_failure_on_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(_verified, "_read_back", lambda path: b"corrupted")

    def bad_unlink(path):
        raise OSError("injected unlink failure")

    monkeypatch.setattr(os, "unlink", bad_unlink)
    target = tmp_path / "x.bin"
    assert _verified._attempt(str(target), b"intended") is False
    assert not target.exists()


# ------------------------------------------------------------------
# ed25519: seed length, signature length, decoding, and the
# S range check.
# ------------------------------------------------------------------


def test_publickey_rejects_wrong_seed_lengths():
    for bad in (b"", b"short", b"x" * 31, b"x" * 33):
        with pytest.raises(ValueError, match="seed must be 32 bytes"):
            ed25519.publickey(bad)


def test_sign_rejects_wrong_seed_lengths():
    for bad in (b"", b"short", b"x" * 31, b"x" * 33):
        with pytest.raises(ValueError, match="seed must be 32 bytes"):
            ed25519.sign(bad, b"message")


def test_verify_rejects_wrong_lengths():
    pk = b"\x00" * 32
    sig = b"\x00" * 64
    assert ed25519.verify(b"\x00" * 31, b"m", sig) is False
    assert ed25519.verify(b"\x00" * 33, b"m", sig) is False
    assert ed25519.verify(pk, b"m", b"\x00" * 63) is False
    assert ed25519.verify(pk, b"m", b"\x00" * 65) is False


def test_verify_rejects_undecodable_points():
    # Strings of the right length are still not point encodings:
    # decoding them raises, and verify reports False, not a crash.
    assert ed25519.verify("a" * 32, b"m", "b" * 64) is False


def test_verify_rejects_s_out_of_range():
    # S == the group order (and above) is rejected before any
    # curve arithmetic on the signature's scalar.
    sig = b"\x00" * 32 + ed25519._l.to_bytes(32, "little")
    assert ed25519.verify(b"\x00" * 32, b"m", sig) is False
    sig_above = b"\x00" * 32 + (ed25519._l + 1).to_bytes(32, "little")
    assert ed25519.verify(b"\x00" * 32, b"m", sig_above) is False


# ------------------------------------------------------------------
# prov: agent-id collisions, non-dict payloads, derivation
# shapes, and the store-level export.
# ------------------------------------------------------------------


def _record(seq, actor, payload, rtype="note"):
    return {
        "seq": seq,
        "t": "2026-01-01T00:00:00Z",
        "actor": actor,
        "type": rtype,
        "payload": payload,
        "prev_hash": "0" * 64,
        "hash": f"{seq:064x}",
    }


def test_agent_id_collisions_are_disambiguated_in_order():
    records = [
        _record(1, "a b", {}),
        _record(2, "a-b", {}),
        _record(3, "a/b", {}),
        _record(4, "a b", {}),  # repeat: reuses the first id
    ]
    out = prov.export_prov(records, "f" * 64)
    agents = out["document"]["agent"]
    assert set(agents) == {"el:agent-a-b", "el:agent-a-b-2", "el:agent-a-b-3"}
    assert agents["el:agent-a-b"]["el:actorName"] == "a b"
    assert agents["el:agent-a-b-2"]["el:actorName"] == "a-b"
    assert agents["el:agent-a-b-3"]["el:actorName"] == "a/b"


def test_non_dict_payload_declares_no_derivations():
    records = [
        _record(1, "alice", "a plain string payload"),
        _record(2, "alice", ["a", "list", "payload"], rtype="decision"),
    ]
    out = prov.export_prov(records, "f" * 64)
    assert out["document"]["wasDerivedFrom"] == {}
    assert out["header"]["derivations"] == 0


def test_derivation_fields_with_wrong_shapes_are_ignored():
    records = [
        _record(1, "alice", {"derived_from": 7}),
        _record(2, "alice", {"basis": "not-a-list"}, rtype="decision"),
        _record(3, "alice", {"derived_from": ["x", None, 1.5]}),
        _record(4, "alice", {"basis": [1, "y"]}, rtype="decision"),
    ]
    out = prov.export_prov(records, "f" * 64)
    # Only record 4's integer basis entry survives.
    derived = out["document"]["wasDerivedFrom"]
    assert list(derived.values()) == [
        {"prov:generatedEntity": "el:record-4", "prov:usedEntity": "el:record-1"}
    ]
    assert out["header"]["derivations"] == 1


def _fake_core(monkeypatch, records):
    fake = types.ModuleType("epistemic_ledger._core")
    fake.read_records_json = lambda store_dir: json.dumps(records)
    monkeypatch.setitem(sys.modules, "epistemic_ledger._core", fake)


def test_export_store_prov_empty_store(monkeypatch):
    _fake_core(monkeypatch, [])
    out = prov.export_store_prov("/anywhere")
    assert out["header"]["records"] == 0
    assert out["header"]["head_hash"] == "0" * 64


def test_export_store_prov_uses_last_record_hash(monkeypatch):
    records = [_record(1, "alice", {}), _record(2, "bob", {})]
    _fake_core(monkeypatch, records)
    sth = {"checkpoint_seq": 1}
    out = prov.export_store_prov("/anywhere", sth)
    assert out["header"]["records"] == 2
    assert out["header"]["head_hash"] == records[-1]["hash"]
    assert out["header"]["sth"] == sth


# ------------------------------------------------------------------
# partitions: the containment check fires if a tenant id ever
# resolves outside the root (defense in depth behind the slug
# rule, exercised here with the slug check bypassed).
# ------------------------------------------------------------------


def test_partition_dir_containment_check_fires(monkeypatch, tmp_path):
    monkeypatch.setattr(partitions, "validate_tenant_id", lambda tenant_id: tenant_id)
    with pytest.raises(ValueError, match="resolves outside the partitions root"):
        partitions.partition_dir(str(tmp_path), "../escape")


# ------------------------------------------------------------------
# pattern: log reading failures, folds over unknown claims,
# the empty-decisions map rendering, and the live-ledger gate.
# ------------------------------------------------------------------


def test_events_from_log_missing_file_is_empty(tmp_path):
    assert pattern.events_from_log(str(tmp_path / "no-such-dir")) == []
    assert pattern.events_from_log(str(tmp_path)) == []  # dir exists, file does not


def test_events_from_log_reads_valid_lines_and_skips_blanks(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text('{"type": "assert", "n": 1}\n\n{"type": "decision"}\n')
    events = pattern.events_from_log(str(tmp_path))
    assert [e["type"] for e in events] == ["assert", "decision"]


def test_events_from_log_names_the_bad_line(tmp_path):
    log = tmp_path / "events.jsonl"
    log.write_text('{"ok": true}\nthis is not json\n')
    with pytest.raises(ValueError, match="line 2"):
        pattern.events_from_log(str(tmp_path))


def _assert_event(claim_id="c1", prior=0.5):
    return {
        "type": "assert",
        "event_id": "e1",
        "t": "2026-01-01T00:00:00Z",
        "payload": {"claim_id": claim_id, "statement": "s", "prior": prior},
    }


def test_build_matrix_ignores_revisions_of_unknown_claims():
    events = [
        _assert_event(),
        {"type": "score_revision", "payload": {"claim_id": "ghost", "new_score": 0.9}},
        {
            "type": "supersede",
            "payload": {"old_claim_id": "ghost", "new_claim_id": "c2"},
        },
        {
            "type": "claim_status_changed",
            "payload": {"claim_id": "ghost", "status": "dead"},
        },
    ]
    matrix = pattern.build_matrix(events)
    assert len(matrix["claims"]) == 1
    row = matrix["claims"][0]
    assert row["status"] == "active"
    assert row["confidence"] == 0.5
    assert row["superseded_by"] is None
    assert matrix["counts"] == {"active": 1}


def test_map_markdown_without_decisions_says_none():
    text = pattern.map_markdown(pattern.build_map([_assert_event()]))
    assert "- none" in text
    assert "## Decisions" in text


class _FakeLedger:
    def __init__(self, events):
        self._stored = events

    def _events(self):
        return list(self._stored)


def test_check_pattern_for_ledger_uses_the_ledgers_events():
    events = [_assert_event()]
    ledger = _FakeLedger(events)
    good_matrix = pattern.matrix_json(pattern.build_matrix(events))
    good_map = pattern.map_json(pattern.build_map(events))
    assert pattern.check_pattern_for_ledger(ledger, good_matrix, good_map) == {
        "ok": True,
        "problems": [],
    }
    bad = pattern.check_pattern_for_ledger(ledger, good_matrix, "{}")
    assert bad["ok"] is False
    assert bad["problems"] == ["map diverges from the ledger (regenerate it)"]
