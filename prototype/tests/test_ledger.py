"""Tests for the living epistemic ledger v0.1 prototype."""

import os
import shutil
import tempfile

import pytest

from ledger import Ledger, jeffrey


@pytest.fixture
def ledger():
    d = tempfile.mkdtemp()
    yield Ledger(d)
    shutil.rmtree(d)


def test_jeffrey_math():
    # Certain evidence for E: posterior collapses to P(H|E).
    assert jeffrey(0.5, 0.9, 0.1, 1.0) == pytest.approx(0.9)
    # Certain evidence against E: posterior collapses to P(H|~E).
    assert jeffrey(0.5, 0.9, 0.1, 0.0) == pytest.approx(0.1)
    # Uncertain evidence moves partway.
    assert jeffrey(0.5, 0.9, 0.1, 0.5) == pytest.approx(0.5)


def test_assert_and_live_claim(ledger):
    cid = ledger.assert_claim("the sky is blue", 0.95, t="2026-01-01T00:00:00+00:00")
    row = ledger._live_claim(cid)
    assert row["statement"] == "the sky is blue"
    assert row["score"] == pytest.approx(0.95)
    assert row["status"] == "active"


def test_bitemporal_supersede(ledger):
    c1 = ledger.assert_claim("old claim", 0.6, t="2026-01-01T00:00:00+00:00")
    c2 = ledger.supersede(c1, "corrected claim", 0.8,
                          t="2026-02-01T00:00:00+00:00")
    assert c1 != c2
    # Old claim has no live row (correct bitemporal behavior); its closed
    # version is marked superseded, and the new claim is live.
    closed = ledger.db.execute(
        "SELECT * FROM claims WHERE claim_id = ? AND txn_to IS NOT NULL",
        (c1,)).fetchone()
    assert closed["status"] == "superseded"
    assert ledger._live_claim(c1) is None
    assert ledger._live_claim(c2)["score"] == pytest.approx(0.8)
    # Time travel: at January we believed the old claim.
    jan = {r["claim_id"] for r in
           ledger.believed_at("2026-01-15T00:00:00+00:00")}
    assert c1 in jan and c2 not in jan
    # At March we believe the corrected one.
    mar = {r["claim_id"] for r in
           ledger.believed_at("2026-03-01T00:00:00+00:00")}
    assert c2 in mar and c1 not in mar


def test_revisit_propagates_with_jeffrey(ledger):
    c = ledger.assert_claim("bridge design is safe", 0.6,
                            t="2026-01-01T00:00:00+00:00")
    report = ledger.ingest_evidence(
        "load test passed", 0.9, t="2026-01-02T00:00:00+00:00")
    fact = report["fact_id"]
    ledger.add_support(c, fact, "evidential", p_given=0.95, p_given_not=0.3,
                       t="2026-01-03T00:00:00+00:00")
    # Re-run the revisit now that the support edge exists.
    report = ledger._revisit(fact, {fact: 0.9},
                             t="2026-01-04T00:00:00+00:00")
    assert report["n_revisited"] == 1
    new = ledger._live_claim(c)["score"]
    assert new == pytest.approx(0.95 * 0.9 + 0.3 * 0.1)  # 0.885
    assert new > 0.6


def test_early_cutoff_stops_propagation(ledger):
    a = ledger.assert_claim("A", 0.5, t="2026-01-01T00:00:00+00:00")
    b = ledger.assert_claim("B", 0.5, t="2026-01-01T00:00:00+00:00")
    fact = ledger.assert_claim("F", 0.51, t="2026-01-02T00:00:00+00:00")
    # Weak likelihoods: the update (0.0051) is below epsilon -> cutoff.
    ledger.add_support(a, fact, "evidential", p_given=0.51, p_given_not=0.50,
                       t="2026-01-03T00:00:00+00:00")
    ledger.add_support(b, a, "deductive", p_given=1.0, p_given_not=0.0,
                       t="2026-01-03T00:00:00+00:00")
    report = ledger._revisit(fact, {fact: 0.51},
                             t="2026-01-04T00:00:00+00:00", epsilon=0.01)
    assert report["n_revisited"] == 0
    assert report["cutoff_skipped"] >= 1
    # B never moved because A never moved.
    assert ledger._live_claim(b)["score"] == pytest.approx(0.5)


def test_materiality_flags(ledger):
    c = ledger.assert_claim("C", 0.5, materiality=0.05,
                            t="2026-01-01T00:00:00+00:00")
    fact = ledger.assert_claim("F", 0.9, t="2026-01-02T00:00:00+00:00")
    ledger.add_support(c, fact, "evidential", p_given=0.9, p_given_not=0.1,
                       t="2026-01-03T00:00:00+00:00")
    report = ledger._revisit(fact, {fact: 0.9},
                             t="2026-01-04T00:00:00+00:00")
    assert len(report["flags"]) == 1  # delta 0.32 >= 0.05


def test_queries(ledger):
    c1 = ledger.assert_claim("first", 0.5, t="2026-01-01T00:00:00+00:00")
    c2 = ledger.assert_claim("second", 0.5, t="2026-02-01T00:00:00+00:00")
    ledger.add_support(c2, c1, "deductive", t="2026-02-02T00:00:00+00:00")

    # CHANGED: only February events.
    feb = ledger.changed("2026-02-01T00:00:00+00:00",
                         "2026-03-01T00:00:00+00:00")
    assert all(e["t"] >= "2026-02-01T00:00:00+00:00" for e in feb)
    assert not any(e["payload"].get("statement") == "first" for e in feb)

    # DEPENDS_ON: c2 depends on c1.
    assert ledger.depends_on(c1) == [c2]

    # WHY: c2's support set.
    why = ledger.why(c2)
    assert len(why) == 1 and why[0]["supports_id"] == c1
    assert why[0]["kind"] == "deductive"


def test_retract_support_keeps_claim_while_justified(ledger):
    c = ledger.assert_claim("C", 0.5, t="2026-01-01T00:00:00+00:00")
    f1 = ledger.assert_claim("F1", 0.9, t="2026-01-01T00:00:00+00:00")
    f2 = ledger.assert_claim("F2", 0.9, t="2026-01-01T00:00:00+00:00")
    ledger.add_support(c, f1, "evidential", t="2026-01-02T00:00:00+00:00")
    ledger.add_support(c, f2, "evidential", t="2026-01-02T00:00:00+00:00")
    ledger.retract_support(c, f1, t="2026-01-03T00:00:00+00:00")
    why = ledger.why(c)
    assert [w["supports_id"] for w in why] == [f2]


def test_kill_metrics(ledger):
    c = ledger.assert_claim("C", 0.7, t="2026-01-01T00:00:00+00:00")
    fact = ledger.assert_claim("F", 0.9, t="2026-01-02T00:00:00+00:00")
    ledger.add_support(c, fact, "evidential", p_given=0.9, p_given_not=0.1,
                       t="2026-01-03T00:00:00+00:00")
    ledger._revisit(fact, {fact: 0.9}, t="2026-01-04T00:00:00+00:00")
    ledger.record_outcome(c, True, t="2026-01-05T00:00:00+00:00")
    ledger.manual_score(c, 0.99, actor="human", t="2026-01-06T00:00:00+00:00")

    m = ledger.kill_metrics()
    assert m["fanout"]["n_claims"] == 2
    assert m["brier"] is not None and 0.0 <= m["brier"] <= 1.0
    assert m["n_manual_overrides"] == 1
    assert m["override_rate"] == pytest.approx(1 / m["n_score_revisions"])
    assert len(m["trigger_log"]) == 1
    # Churn: scores moved twice in the same direction -> no sign change.
    assert m["churn"][c] == 0


def test_llm_support_kind_flagged(ledger):
    c = ledger.assert_claim("C", 0.5, t="2026-01-01T00:00:00+00:00")
    f = ledger.assert_claim("F", 0.8, t="2026-01-01T00:00:00+00:00")
    ledger.add_support(c, f, "llm-generated", p_given=0.8, p_given_not=0.4,
                       t="2026-01-02T00:00:00+00:00")
    assert ledger.why(c)[0]["kind"] == "llm-generated"


# ----------------------------------------------------------------------
# v0.2: entrenchment-based contradiction resolution (Design Memo 02)
# ----------------------------------------------------------------------

from ledger import ENTRENCHMENT_TIERS  # noqa: E402


def test_entrenchment_tiers(ledger):
    c = ledger.assert_claim("C", 0.5, t="2026-01-01T00:00:00+00:00")
    old, new = ledger.apply_tier(c, "provisional",
                                 t="2026-01-02T00:00:00+00:00")
    assert (old, new) == (0.5, 0.25)
    assert ledger._live_claim(c)["entrenchment"] == pytest.approx(0.25)
    assert ledger._live_claim(c)["score"] == pytest.approx(0.5)  # untouched
    with pytest.raises(KeyError):
        ledger.apply_tier(c, "nonsense")
    with pytest.raises(ValueError):
        ledger.set_entrenchment(c, 1.5)
    # bitemporal: the old entrenchment is still queryable
    jan = {r["claim_id"]: r for r in
           ledger.believed_at("2026-01-01T12:00:00+00:00")}
    assert jan[c]["entrenchment"] == pytest.approx(0.5)


def test_contradiction_resolution(ledger):
    a = ledger.assert_claim("A: steel frame", 0.90,
                            t="2026-01-01T00:00:00+00:00")
    b = ledger.assert_claim("B: timber frame", 0.85,
                            t="2026-01-01T00:00:00+00:00")
    ledger.apply_tier(a, "measured", t="2026-01-02T00:00:00+00:00")    # 0.75
    ledger.apply_tier(b, "provisional", t="2026-01-02T00:00:00+00:00")  # 0.25
    cid = ledger.declare_contradiction(a, b, actor="human",
                                       t="2026-01-03T00:00:00+00:00")
    assert len(ledger.open_contradictions()) == 1
    res = ledger.resolve_contradiction(cid, t="2026-01-04T00:00:00+00:00")
    assert res["resolved"] is True
    assert res["loser"] == b and res["winner"] == a
    # Jeffrey against the winner: P(B|A)=0.05, P(B|~A)=0.85, P(A)=0.90
    assert res["new"] == pytest.approx(0.05 * 0.90 + 0.85 * 0.10)
    assert ledger._live_claim(b)["score"] == pytest.approx(res["new"])
    assert ledger._live_claim(a)["score"] == pytest.approx(0.90)  # untouched
    assert ledger.open_contradictions() == []
    # resolving again is a no-op
    assert ledger.resolve_contradiction(cid)["already"] is True


def test_contradiction_tie_goes_to_human(ledger):
    a = ledger.assert_claim("A", 0.9, t="2026-01-01T00:00:00+00:00")
    b = ledger.assert_claim("B", 0.9, t="2026-01-01T00:00:00+00:00")
    cid = ledger.declare_contradiction(a, b, t="2026-01-02T00:00:00+00:00")
    res = ledger.resolve_contradiction(cid, t="2026-01-03T00:00:00+00:00")
    assert res["resolved"] is False and res["reason"] == "tie"
    assert len(ledger.open_contradictions()) == 1
    assert ledger._live_claim(a)["score"] == pytest.approx(0.9)
    assert ledger._live_claim(b)["score"] == pytest.approx(0.9)
    m = ledger.kill_metrics()
    assert m["n_open_contradictions"] == 1


def test_contradiction_propagates_to_dependents(ledger):
    a = ledger.assert_claim("A", 0.90, t="2026-01-01T00:00:00+00:00")
    b = ledger.assert_claim("B", 0.85, t="2026-01-01T00:00:00+00:00")
    c = ledger.assert_claim("C: project viable", 0.80,
                            t="2026-01-01T00:00:00+00:00")
    ledger.apply_tier(a, "measured", t="2026-01-02T00:00:00+00:00")
    ledger.apply_tier(b, "provisional", t="2026-01-02T00:00:00+00:00")
    ledger.add_support(c, b, "evidential", p_given=0.95, p_given_not=0.40,
                       t="2026-01-02T00:00:00+00:00")
    cid = ledger.declare_contradiction(a, b, t="2026-01-03T00:00:00+00:00")
    res = ledger.resolve_contradiction(cid, t="2026-01-04T00:00:00+00:00")
    assert res["resolved"] is True
    # C depended on B; B contracted -> C weakens too.
    assert ledger._live_claim(c)["score"] < 0.80
    # And the contraction is visible in the change log.
    types = {e["type"] for e in ledger.changed("2026-01-03T00:00:00+00:00",
                                              "2026-01-05T00:00:00+00:00")}
    assert {"contradiction", "contract", "contradiction_resolved",
            "score_revision"} <= types
