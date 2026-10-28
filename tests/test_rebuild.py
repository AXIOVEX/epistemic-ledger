"""Projection rebuild (DESIGN-13 section 7): the log is ground
truth and ledger.db is a fold of it. A randomized operation
script builds a store through the live write path; the projection
is then deleted, rebuilt from the log alone, and every table must
come back identical — the fold is a transcription of the write
path, and this test is what proves the transcription.

For pre-0.13 logs the assert/policy events lack some fields; the
fold's documented fallbacks apply there, and the second test pins
the guarantee that survives every era: scores and verification.
"""

import os
import random
import sqlite3

import pytest

from epistemic_ledger import Ledger

TABLES = (
    "claims",
    "support_edges",
    "outcomes",
    "claim_intervals",
    "claim_combos",
    "writers",
    "policies",
    "graphs",
    "claim_graphs",
    "claim_topics",
)


def _dump(path):
    db = sqlite3.connect(os.path.join(path, "ledger.db"))
    db.row_factory = sqlite3.Row
    out = {}
    for table in TABLES:
        rows = db.execute(f"SELECT * FROM {table}").fetchall()
        out[table] = sorted(tuple(dict(r).values()) for r in rows)
    db.close()
    return out


def _script(seed):
    rng = random.Random(seed)
    return rng


def _build_store(path):
    led = Ledger(path)
    rng = _script(20261028)
    led.register_writer("amy", "owner")
    led.register_writer("bob", "provisional")
    led.register_policy("review-gate", "a second policy", version=1)
    led.register_graph("sensitive", 0.4)
    ids = []
    for i in range(14):
        cid = led.assert_claim(
            f"claim {i}",
            round(rng.uniform(0.1, 0.9), 3),
            writer="amy" if i % 3 == 0 else None,
            critical=bool(i % 5 == 0),
            materiality=0.2 if i % 4 == 0 else 0.05,
        )
        ids.append(cid)
    for i in range(1, 14):
        led.add_support(
            ids[i],
            ids[i - 1],
            "evidential",
            p_given=0.9,
            p_given_not=0.2,
            strength=0.8,
        )
    led.add_support(ids[5], ids[0], "deductive", p_given=1.0, p_given_not=0.0)
    led.set_combo(ids[5], "noisy-or", leak=0.1, strengths={ids[0]: 0.5})
    led.retract_support(ids[5], ids[0])
    led.manual_score(ids[0], 0.33)
    led.ingest_evidence("a fact arrives", 0.8)
    led.set_entrenchment(ids[2], 0.9)
    led.assign_topic(ids[3], "bridges")
    led.assign_graph(ids[4], "sensitive")
    led.set_interval(ids[6], 0.3, 0.8)
    led.combine_interval(ids[6], 0.5, 0.2, 0.3)
    led.record_outcome(ids[1], True)
    led.record_outcome(ids[1], False)
    new_id = led.supersede(
        ids[7], "claim 7, corrected", 0.6, reason="typo in v1", source="review"
    )
    led.set_claim_status(ids[8], "dead", reason="moot", source="review")
    led.record_decision("ship it", [ids[3], new_id])
    led.declare_contradiction(ids[9], ids[10], writer="amy")
    scores = {cid: led.get_score(cid) for cid in ids + [new_id]}
    led.close()
    return scores


def test_rebuild_reproduces_projection_exactly(tmp_path):
    path = str(tmp_path / "store")
    scores = _build_store(path)
    before = _dump(path)
    os.remove(os.path.join(path, "ledger.db"))
    report = Ledger.rebuild_projection(path)
    assert report["ok"] is True
    assert _dump(path) == before
    led = Ledger(path)
    assert {cid: led.get_score(cid) for cid in scores} == scores
    assert led.verify_store()["ok"] is True
    led.close()


def test_rebuild_refuses_unknown_event_types(tmp_path):
    path = str(tmp_path / "store")
    _build_store(path)
    with open(os.path.join(path, "events.jsonl"), "a", encoding="utf-8") as f:
        f.write(
            '{"event_id": "Exyz", "t": "2026-06-01T00:00:00+00:00",'
            ' "actor": "system", "type": "from_the_future", "payload": {}}\n'
        )
    with pytest.raises(ValueError, match="from_the_future"):
        Ledger.rebuild_projection(path)
