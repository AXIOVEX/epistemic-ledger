"""Targeted branch-arc tests for ledger.py.

Each test builds the specific graph or store shape a branch arc
needs (truncation interplay in impact's path layering, decision
bookkeeping, BFS revisits) and asserts the observable result.
"""

import pytest

import epistemic_ledger.ledger as ledger_module
from epistemic_ledger.ledger import Ledger

T1 = "2026-01-01T00:00:00+00:00"
T2 = "2026-01-02T00:00:00+00:00"


@pytest.fixture
def ledger(tmp_path):
    L = Ledger(str(tmp_path / "store"))
    yield L
    L.close()


def _chain(ledger, n):
    """root -> c1 -> c2 -> ... (each claim supported by the previous)."""
    ids = [ledger.assert_claim("root", 0.5, t=T1)]
    for i in range(n):
        cid = ledger.assert_claim(f"c{i + 1}", 0.5, t=T1)
        ledger.add_support(cid, ids[-1], "evidential", t=T1)
        ids.append(cid)
    return ids


def test_open_close_and_failed_recovery_without_fcntl(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger_module, "fcntl", None)
    L = Ledger(str(tmp_path / "nolock"))
    assert L._lock_file is None
    L.close()  # the no-lock-file close path

    def boom(self):
        raise RuntimeError("unrecoverable")

    monkeypatch.setattr(Ledger, "_recover_at_open", boom)
    with pytest.raises(RuntimeError, match="unrecoverable"):
        Ledger(str(tmp_path / "nolock2"))


def test_verify_verdict_signatures_unknown_signer(ledger):
    ledger._emit(
        "contradiction_dismissed",
        {
            "held_id": "H1",
            "signer": "never-registered",
            "signature": "ab" * 32,
            "signed_message": "anything",
        },
        actor="system",
        t=T2,
    )
    result = ledger.verify_verdict_signatures()
    assert result["checked"] == 1
    assert result["valid"] == 0
    assert len(result["invalid"]) == 1


def test_detect_contradictions_ignores_unknown_resolution(ledger):
    ledger._emit(
        "contradiction_resolved",
        {"contradiction_id": "no-such-contradiction"},
        actor="system",
        t=T1,
    )
    a = ledger.assert_claim("later event a", 0.5, t=T2)
    b = ledger.assert_claim("later event b", 0.5, t=T2)
    assert ledger.detect_contradictions() == []
    assert a != b


def test_detect_contradictions_low_conflict_same_topic(ledger):
    a = ledger.assert_claim("claim a", 0.5, t=T1)
    b = ledger.assert_claim("claim b", 0.5, t=T1)
    ledger.set_interval(a, 0.90, 0.95, t=T1)
    ledger.set_interval(b, 0.85, 0.90, t=T1)
    ledger.assign_topic(a, "prop:x", t=T1)
    ledger.assign_topic(b, "prop:x", t=T1)
    # Same topic, intervals close: the conflict K is computed and
    # falls below the bar, so nothing is declared.
    assert ledger.detect_contradictions(topic_of=ledger.get_topic) == []


def test_claim_dict_with_none_fields():
    d = Ledger._claim_dict(
        {"score": None, "materiality": 2, "entrenchment": 0.5, "critical": None}
    )
    assert d["score"] is None
    assert d["materiality"] == 2.0
    assert d["entrenchment"] == 0.5
    assert d["critical"] is None


def test_impact_decision_over_depth_after_claim_over_depth(ledger):
    root, a, b = _chain(ledger, 2)
    ledger.record_decision("d", [a], t=T2)
    result = ledger.impact(root, max_depth=1)
    assert result["truncated"] is True
    assert result["truncation_reasons"] == ["max_depth"]


def test_impact_unkept_decisions_in_path_layering(ledger):
    root, a = _chain(ledger, 1)
    ledger.record_decision("d1", [a], t=T2)
    ledger.record_decision("d2", [a], t=T2)
    result = ledger.impact(root, max_results=1)
    assert result["truncated"] is True
    assert "max_results" in result["truncation_reasons"]


def test_impact_far_parent_dropped_but_decision_kept(ledger):
    ids = _chain(ledger, 5)
    root, a, e = ids[0], ids[1], ids[5]
    did = ledger.record_decision("d", [a, e], t=T2)
    result = ledger.impact(root, max_results=3)
    node_ids = {entry["id"] for entry in result["nodes"]}
    assert did in node_ids  # the decision survived the cap
    assert e not in node_ids  # its far parent did not


def test_impact_decision_child_with_nearer_other_parent(ledger):
    ids = _chain(ledger, 3)
    root, a, c = ids[0], ids[1], ids[3]
    ledger.record_decision("d", [a, c], t=T2)
    result = ledger.impact(root)
    assert result["truncated"] is False


def test_impact_propagated_with_unrelated_co_supporter(ledger):
    root = ledger.assert_claim("root", 0.9, t=T1)
    other = ledger.assert_claim("unrelated", 0.9, t=T1)
    b = ledger.assert_claim("jointly supported", 0.5, t=T1)
    ledger.add_support(b, root, "evidential", p_given=0.9, p_given_not=0.2, t=T1)
    ledger.add_support(b, other, "evidential", p_given=0.9, p_given_not=0.2, t=T1)
    result = ledger.impact(root, mode="propagated", revised_score=0.0)
    moved = {m["claim_id"] for m in result["movements"]}
    assert b in moved


def test_impact_propagated_combo_with_unmoved_parent(ledger):
    root = ledger.assert_claim("root", 0.9, t=T1)
    other = ledger.assert_claim("unrelated", 0.8, t=T1)
    combo = ledger.assert_claim("combo claim", 0.5, t=T1)
    ledger.add_support(combo, root, "evidential", t=T1)
    ledger.add_support(combo, other, "evidential", t=T1)
    ledger.set_combo(combo, "noisy-or", t=T1)
    result = ledger.impact(root, mode="propagated", revised_score=0.0)
    moved = {m["claim_id"] for m in result["movements"]}
    assert combo in moved


def test_kill_metrics_fanout_diamond(ledger):
    d = ledger.assert_claim("base fact", 0.9, t=T1)
    b = ledger.assert_claim("mid b", 0.5, t=T1)
    c = ledger.assert_claim("mid c", 0.5, t=T1)
    a = ledger.assert_claim("top", 0.5, t=T1)
    ledger.add_support(b, d, "evidential", t=T1)
    ledger.add_support(c, d, "evidential", t=T1)
    ledger.add_support(a, b, "evidential", t=T1)
    ledger.add_support(a, c, "evidential", t=T1)
    metrics = ledger.kill_metrics()
    # From the top claim the BFS reaches b, c, and the shared base
    # exactly once: fanout 3.
    assert metrics["fanout"]["max"] >= 3
