"""DESIGN-17 stage 4: the layered map (P4).

The map renders exactly the generated data: its headline
equals the ledger's verified headline state, its groups
partition the claim set, its decisions carry their basis,
and every evidence entry names real events from the log.
"""

from epistemic_ledger.ledger import Ledger
from epistemic_ledger.pattern import (
    build_map,
    map_from_ledger,
    map_json,
    map_markdown,
    matrix_from_ledger,
)

T1 = "2026-06-01T00:00:00+00:00"
T2 = "2026-06-02T00:00:00+00:00"


def _ledger(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    a = led.assert_claim("claim a", 0.8, t=T1)
    b = led.assert_claim("claim b", 0.6, t=T1)
    led.add_support(a, b, "evidential", t=T2)
    led.manual_score(a, 0.7)
    d = led.record_decision("ship it", [a], t=T2)
    dead = led.assert_claim("claim dead", 0.3, t=T2)
    led.set_claim_status(dead, "dead", reason="moot", source="review", t=T2)
    led.close()
    return a, b, d, dead


def test_headline_equals_verified_state(tmp_path):
    a, b, d, dead = _ledger(tmp_path)
    led = Ledger(str(tmp_path / "store"))
    m = map_from_ledger(led)
    check = led.verify_store()
    assert check["ok"] is True
    assert m["headline"]["events"] == check["events"]
    assert m["headline"]["claims"] == 3
    assert m["headline"]["decisions"] == 1
    assert m["headline"]["counts"] == matrix_from_ledger(led)["counts"]
    led.close()


def test_groups_partition_the_claims(tmp_path):
    a, b, d, dead = _ledger(tmp_path)
    led = Ledger(str(tmp_path / "store"))
    m = map_from_ledger(led)
    grouped = [cid for g in m["groups"] for cid in g["claim_ids"]]
    assert sorted(grouped) == sorted([a, b, dead])
    assert len(grouped) == len(set(grouped))  # disjoint
    by_status = {g["status"]: g["claim_ids"] for g in m["groups"]}
    assert by_status["active"] == [a, b]
    assert by_status["dead"] == [dead]
    led.close()


def test_decisions_and_evidence_trace_to_the_log(tmp_path):
    a, b, d, dead = _ledger(tmp_path)
    led = Ledger(str(tmp_path / "store"))
    events = led._events()
    log_ids = {e["event_id"] for e in events}
    m = map_from_ledger(led)
    dec = m["decisions"][0]
    assert dec["decision_id"] == d
    assert dec["basis"] == [a]
    assert dec["event_id"] in log_ids
    evidence = {e["claim_id"]: e["events"] for e in m["evidence"]}
    assert set(evidence) == {a, b, dead}
    for ids in evidence.values():
        assert ids and all(i in log_ids for i in ids)
    # The support event touches both endpoints.
    support_id = next(e["event_id"] for e in events if e["type"] == "support")
    assert support_id in evidence[a]
    assert support_id in evidence[b]
    # Each claim's own assert event is in its evidence.
    for cid in (a, b, dead):
        assert_id = next(
            e["event_id"]
            for e in events
            if e["type"] == "assert" and e["payload"]["claim_id"] == cid
        )
        assert assert_id in evidence[cid]
    led.close()


def test_map_regeneration_is_byte_identical(tmp_path):
    _ledger(tmp_path)
    led = Ledger(str(tmp_path / "store"))
    events = led._events()
    assert map_json(build_map(events)) == map_json(build_map(events))
    md = map_markdown(build_map(events))
    assert md == map_markdown(build_map(events))
    assert md.startswith("# Ledger map (generated — do not edit)")
    assert "ship it" in md
    led.close()
