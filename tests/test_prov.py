"""PROV export (DESIGN-15 D6, claim V1, unit level).

The mapping over synthetic record dicts: one entity and one
activity per record, agents deduplicated by actor, derivations
only where a record declares them, the header carrying the
head hash, and byte-identical re-export. The store-level
accounting drill lives in the battery.
"""

from __future__ import annotations

import json

from epistemic_ledger import prov

RECORDS = [
    {
        "seq": 1,
        "t": "2026-01-01T00:00:00Z",
        "actor": "alice",
        "type": "note",
        "payload": {"text": "first"},
        "prev_hash": "0" * 64,
        "hash": "a" * 64,
    },
    {
        "seq": 2,
        "t": "2026-01-01T00:01:00Z",
        "actor": "bob@example.org",
        "type": "decision",
        "payload": {"label": "ship it", "basis": [1]},
        "prev_hash": "a" * 64,
        "hash": "b" * 64,
    },
    {
        "seq": 3,
        "t": "2026-01-01T00:02:00Z",
        "actor": "alice",
        "type": "note",
        "payload": {"text": "follows", "derived_from": [2]},
        "prev_hash": "b" * 64,
        "hash": "c" * 64,
    },
]


def test_mapping_accounts_for_every_record():
    out = prov.export_prov(RECORDS, "c" * 64)
    doc = out["document"]
    assert len(doc["entity"]) == 3
    assert len(doc["activity"]) == 3
    assert len(doc["wasGeneratedBy"]) == 3
    assert len(doc["wasAssociatedWith"]) == 3
    assert set(doc["agent"]) == {"el:agent-alice", "el:agent-bob-example.org"}
    assert out["header"]["records"] == 3
    assert out["header"]["head_hash"] == "c" * 64
    assert out["header"]["sth"] is None


def test_actor_name_preserved_exactly():
    out = prov.export_prov(RECORDS, "c" * 64)
    agent = out["document"]["agent"]["el:agent-bob-example.org"]
    assert agent["el:actorName"] == "bob@example.org"


def test_derivations_only_where_declared():
    out = prov.export_prov(RECORDS, "c" * 64)
    derived = out["document"]["wasDerivedFrom"]
    pairs = {
        (v["prov:generatedEntity"], v["prov:usedEntity"]) for v in derived.values()
    }
    assert pairs == {("el:record-2", "el:record-1"), ("el:record-3", "el:record-2")}
    assert out["header"]["derivations"] == 2


def test_reexport_is_byte_identical():
    one = json.dumps(prov.export_prov(RECORDS, "c" * 64), sort_keys=True)
    two = json.dumps(prov.export_prov(RECORDS, "c" * 64), sort_keys=True)
    assert one == two


def test_dangling_derivation_is_not_invented():
    records = [dict(RECORDS[0], payload={"derived_from": [99]})]
    out = prov.export_prov(records, "a" * 64)
    assert out["document"]["wasDerivedFrom"] == {}
    assert out["header"]["derivations"] == 0
