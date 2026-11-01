"""DESIGN-17 stage 2: the pattern fields on claims (P1, P2).

source, falsifier, and does_not_establish are first-class,
optional claim fields: carried on the claim row and the
assert event, preserved by score revisions and by a full
projection rebuild, and restated (never silently inherited)
on supersede. Claims asserted without them read back None,
and pre-0.15 logs fold with None fields.
"""

import json
import os

from epistemic_ledger.ledger import Ledger

FIELDS = {
    "source": "nightly stress tier, run 5",
    "falsifier": "a green tier run whose soak reports errors",
    "does_not_establish": "durability under power loss",
}


def _events(path):
    with open(os.path.join(path, "events.jsonl"), encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_fields_round_trip_through_reads_and_rebuild(tmp_path):
    path = str(tmp_path / "store")
    led = Ledger(path)
    cid = led.assert_claim("the soak is stable", 0.8, **FIELDS)
    got = led.get_claim(cid)
    for key, want in FIELDS.items():
        assert got[key] == want, key
    # The assert event itself carries the fields (P1).
    ev = next(e for e in _events(path) if e["type"] == "assert")
    for key, want in FIELDS.items():
        assert ev["payload"][key] == want, key
    # A score revision (a new bitemporal version) keeps them.
    led.manual_score(cid, 0.6)
    got = led.get_claim(cid)
    for key, want in FIELDS.items():
        assert got[key] == want, key
    led.close()
    # A full projection rebuild keeps them (P1).
    os.remove(os.path.join(path, "ledger.db"))
    report = Ledger.rebuild_projection(path)
    assert report["ok"] is True
    led = Ledger(path)
    got = led.get_claim(cid)
    for key, want in FIELDS.items():
        assert got[key] == want, key
    led.close()


def test_fieldless_claim_reads_none(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    cid = led.assert_claim("plain claim", 0.5)
    got = led.get_claim(cid)
    assert got["source"] is None
    assert got["falsifier"] is None
    assert got["does_not_establish"] is None
    led.close()


def test_pre_015_log_folds_with_none_fields(tmp_path):
    # A hand-written assert event without the pattern keys —
    # the shape every pre-0.15 log has — rebuilds cleanly.
    path = str(tmp_path / "store")
    os.makedirs(path)
    with open(os.path.join(path, "events.jsonl"), "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "event_id": "Eold1",
                    "t": "2026-06-01T00:00:00+00:00",
                    "actor": "system",
                    "type": "assert",
                    "payload": {
                        "claim_id": "Cold1",
                        "statement": "old claim",
                        "prior": 0.5,
                        "writer": None,
                    },
                }
            )
            + "\n"
        )
    report = Ledger.rebuild_projection(path)
    assert report["ok"] is True
    led = Ledger(path)
    got = led.get_claim("Cold1")
    assert got["statement"] == "old claim"
    assert got["source"] is None
    assert got["falsifier"] is None
    assert got["does_not_establish"] is None
    led.close()


def test_supersede_is_append_only_and_restates_fields(tmp_path):
    path = str(tmp_path / "store")
    led = Ledger(path)
    cid = led.assert_claim("the soak is stable", 0.8, **FIELDS)
    log_before = open(os.path.join(path, "events.jsonl"), "rb").read()
    new_id = led.supersede(
        cid,
        "the soak is stable at 4h",
        0.9,
        reason="the first statement lacked the duration",
        source="release tier run 5",
        falsifier="a 4h soak report with errors",
    )
    # P2: the original assertion event is byte-identical.
    log_after = open(os.path.join(path, "events.jsonl"), "rb").read()
    assert log_after.startswith(log_before)
    first_assert = next(
        e
        for e in _events(path)
        if e["type"] == "assert" and e["payload"]["claim_id"] == cid
    )
    assert first_assert["payload"]["statement"] == "the soak is stable"
    new = led.get_claim(new_id)
    # The successor's source defaults to the bundle source;
    # its falsifier is the restated one; does_not_establish is
    # NOT inherited from the old claim.
    assert new["source"] == "release tier run 5"
    assert new["falsifier"] == "a 4h soak report with errors"
    assert new["does_not_establish"] is None
    led.close()


def test_supersede_claim_source_overrides_bundle(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    cid = led.assert_claim("v1", 0.5, source="origin-a")
    new_id = led.supersede(
        cid,
        "v2",
        0.6,
        reason="r",
        source="correction-source",
        claim_source="origin-b",
    )
    assert led.get_claim(new_id)["source"] == "origin-b"
    led.close()
