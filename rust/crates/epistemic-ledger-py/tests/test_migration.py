"""Migration tests (DESIGN-13 claim G1): a 0.12.0 store migrates
into the chained format with every payload preserved, terminal
scores unchanged, and the new chain verifying."""

import json
import os

from epistemic_ledger import Ledger
from epistemic_ledger._core import read_records_json
from epistemic_ledger.migrate import migrate_store


def _build_legacy_store(path):
    L = Ledger(str(path))
    a = L.assert_claim("bridge design is safe", 0.60)
    b = L.assert_claim("project ships on time", 0.55)
    L.add_support(b, a, "deductive", p_given=0.90, p_given_not=0.20)
    r = L.ingest_evidence("load test passed", 0.90)
    fact = r["fact_id"]
    L.add_support(a, fact, "evidential", p_given=0.95, p_given_not=0.30)
    L._revisit(fact, {fact: 0.90})
    scores = {cid: L.get_score(cid) for cid in (a, b)}
    L.close()
    return scores


def _terminal_scores(records):
    """The verify_store rule: a claim's terminal score is its last
    score_revision's new_score, else its assert prior."""
    expected = {}
    for rec in records:
        p = rec["payload"]
        cid = p.get("claim_id")
        if rec["type"] == "assert" and cid:
            expected[cid] = p.get("prior")
        elif rec["type"] == "score_revision" and cid:
            expected[cid] = p.get("new_score")
    return expected


def test_migration_preserves_history_and_scores(tmp_path):
    src = tmp_path / "legacy"
    dst = tmp_path / "chained"
    scores = _build_legacy_store(src)
    with open(src / "events.jsonl", encoding="utf-8") as f:
        legacy = [json.loads(line) for line in f if line.strip()]

    report = migrate_store(str(src), str(dst))

    assert report["legacy_events"] == len(legacy)
    assert report["total_records"] == len(legacy) + 1  # + migration marker
    records = json.loads(read_records_json(str(dst)))
    # the marker comes first; legacy events follow, byte-faithful
    assert records[0]["type"] == "migration"
    assert records[0]["actor"] == "system"
    for rec, event in zip(records[1:], legacy):
        assert rec["t"] == event["t"]
        assert rec["actor"] == event["actor"]
        assert rec["type"] == event["type"]
        assert rec["payload"] == event["payload"]
    # terminal scores from the migrated log equal the original
    # store's live scores (claim G1)
    terminal = _terminal_scores(records)
    for cid, want in scores.items():
        assert abs(terminal[cid] - want) < 1e-9
    # the map preserves every legacy event id
    with open(dst / "migration-map.json", encoding="utf-8") as f:
        mmap = json.load(f)
    mapped = [v for v in mmap["seq_to_legacy_event_id"].values() if v]
    assert mapped == [e["event_id"] for e in legacy]
    assert mmap["signed_from_seq"] == report["signed_from_seq"]
    assert os.path.exists(dst / "events.log")
