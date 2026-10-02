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
    # Two revisit passes logged: the explicit evidence revisit, plus the
    # one manual_score runs over dependents since v0.11.1 (c has none,
    # but the pass itself is audited).
    assert len(m["trigger_log"]) == 2
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


# ----------------------------------------------------------------------
# v0.3: learned entrenchment + D-S intervals
# ----------------------------------------------------------------------

def test_learn_entrenchment_from_brier(ledger):
    good = ledger.assert_claim("good", 0.90, t="2026-01-01T00:00:00+00:00")
    bad = ledger.assert_claim("bad", 0.90, t="2026-01-01T00:00:00+00:00")
    thin = ledger.assert_claim("thin", 0.90, t="2026-01-01T00:00:00+00:00")
    for i in range(3):
        ledger.record_outcome(good, True, t=f"2026-02-0{i + 1}T00:00:00+00:00")
        ledger.record_outcome(bad, False, t=f"2026-02-0{i + 1}T00:00:00+00:00")
    ledger.record_outcome(thin, True, t="2026-02-01T00:00:00+00:00")  # only 1
    rep = ledger.learn_entrenchment(t="2026-03-01T00:00:00+00:00")
    by_id = {r["claim_id"]: r for r in rep}
    # Brier 0.01 -> entrenchment 0.99; Brier 0.81 -> 0.19
    assert by_id[good]["new"] == pytest.approx(0.99)
    assert by_id[bad]["new"] == pytest.approx(0.19)
    assert thin not in by_id  # not enough outcomes: manual tier stands
    assert ledger._live_claim(good)["entrenchment"] == pytest.approx(0.99)
    assert ledger._live_claim(good)["score"] == pytest.approx(0.90)  # untouched
    ev = [e for e in ledger._events() if e["type"] == "entrenchment_set"
          and e["payload"].get("learned")]
    assert len(ev) == 2


def test_learn_entrenchment_uses_score_at_outcome_time(ledger):
    c = ledger.assert_claim("C", 0.90, t="2026-01-01T00:00:00+00:00")
    ledger.record_outcome(c, True, t="2026-01-15T00:00:00+00:00")   # at 0.90
    ledger.manual_score(c, 0.20, actor="human",
                        t="2026-02-01T00:00:00+00:00")
    ledger.record_outcome(c, True, t="2026-02-15T00:00:00+00:00")   # at 0.20
    ledger.record_outcome(c, False, t="2026-03-15T00:00:00+00:00")  # at 0.20
    rep = ledger.learn_entrenchment(t="2026-04-01T00:00:00+00:00")
    # Brier = (0.01 + 0.64 + 0.04)/3 = 0.23 -> e = 0.77
    assert rep[0]["new"] == pytest.approx(0.77)


def test_interval_set_and_combine(ledger):
    c = ledger.assert_claim("C", 0.5, t="2026-01-01T00:00:00+00:00")
    assert ledger.ignorance(c) is None
    ledger.set_interval(c, 0.0, 1.0, t="2026-01-02T00:00:00+00:00")  # total ignorance
    assert ledger.ignorance(c) == pytest.approx(1.0)
    # evidence: H=0.8, ~H=0.0, ignorance=0.2, against total ignorance
    # a=(0,0,1): K = 0*0.0 + 0*0.8 = 0; c_h = 0.8, c_nh = 0 -> [0.8, 1.0]
    r = ledger.combine_interval(c, 0.8, 0.0, 0.2,
                                t="2026-01-03T00:00:00+00:00")
    assert r["combined"] is True
    assert r["conflict"] == pytest.approx(0.0)
    assert r["belief"] == pytest.approx(0.8)
    assert r["plausibility"] == pytest.approx(1.0)
    assert ledger.ignorance(c) == pytest.approx(0.2)
    with pytest.raises(ValueError):
        ledger.set_interval(c, 0.7, 0.3)  # belief > plausibility


def test_interval_refuses_pathological_conflict(ledger):
    c = ledger.assert_claim("C", 0.5, t="2026-01-01T00:00:00+00:00")
    ledger.set_interval(c, 0.99, 1.0, t="2026-01-02T00:00:00+00:00")
    # K = 0.99*1.0 = 0.99 -> pathological, refused
    r = ledger.combine_interval(c, 0.0, 1.0, 0.0,
                                t="2026-01-03T00:00:00+00:00")
    assert r["combined"] is False
    assert r["conflict"] == pytest.approx(0.99)
    # interval unchanged after refusal
    assert ledger.get_interval(c) == pytest.approx((0.99, 1.0))


# ----------------------------------------------------------------------
# v0.4: joint likelihoods (Design Memo 05)
# ----------------------------------------------------------------------

def test_noisy_and_semantics(ledger):
    d = ledger.assert_claim("D", 0.5, t="2026-01-01T00:00:00+00:00")
    ps = [ledger.assert_claim(f"P{i}", 0.99, t="2026-01-01T00:00:00+00:00")
          for i in range(3)]
    for p in ps:
        ledger.add_support(d, p, "evidential",
                           t="2026-01-02T00:00:00+00:00")
    ledger.set_combo(d, "noisy-and", t="2026-01-03T00:00:00+00:00")
    # all parents true -> ~1
    r = ledger._revisit(ps[0], {p: 0.99 for p in ps},
                        t="2026-01-04T00:00:00+00:00")
    assert ledger._live_claim(d)["score"] == pytest.approx(0.99 ** 3, abs=1e-6)
    # one parent false -> ~leak (0.0)
    r = ledger._revisit(ps[0], {ps[0]: 0.01, ps[1]: 0.99, ps[2]: 0.99},
                        t="2026-01-05T00:00:00+00:00")
    assert ledger._live_claim(d)["score"] == pytest.approx(0.01 * 0.99 ** 2,
                                                           abs=1e-6)


def test_noisy_or_semantics(ledger):
    d = ledger.assert_claim("D", 0.5, t="2026-01-01T00:00:00+00:00")
    ps = [ledger.assert_claim(f"P{i}", 0.01, t="2026-01-01T00:00:00+00:00")
          for i in range(3)]
    for p in ps:
        ledger.add_support(d, p, "evidential",
                           t="2026-01-02T00:00:00+00:00")
    ledger.set_combo(d, "noisy-or", leak=0.05,
                     t="2026-01-03T00:00:00+00:00")
    # all false -> leak
    ledger._revisit(ps[0], {p: 0.01 for p in ps},
                    t="2026-01-04T00:00:00+00:00")
    assert ledger._live_claim(d)["score"] == pytest.approx(
        1 - 0.95 * (1 - 0.01) ** 3, abs=1e-6)
    # one true -> ~1
    ledger._revisit(ps[0], {ps[0]: 0.99, ps[1]: 0.01, ps[2]: 0.01},
                    t="2026-01-05T00:00:00+00:00")
    assert ledger._live_claim(d)["score"] == pytest.approx(
        1 - 0.95 * (1 - 0.99) * (1 - 0.01) ** 2, abs=1e-6)


def test_combo_strengths_and_leak(ledger):
    d = ledger.assert_claim("D", 0.5, t="2026-01-01T00:00:00+00:00")
    p1 = ledger.assert_claim("P1", 0.99, t="2026-01-01T00:00:00+00:00")
    p2 = ledger.assert_claim("P2", 0.99, t="2026-01-01T00:00:00+00:00")
    ledger.add_support(d, p1, "evidential", t="2026-01-02T00:00:00+00:00")
    ledger.add_support(d, p2, "evidential", t="2026-01-02T00:00:00+00:00")
    # p2 irrelevant (strength 0): D follows p1 alone
    ledger.set_combo(d, "noisy-and", strengths={p2: 0.0},
                     t="2026-01-03T00:00:00+00:00")
    ledger._revisit(p1, {p1: 0.01, p2: 0.99},
                    t="2026-01-04T00:00:00+00:00")
    assert ledger._live_claim(d)["score"] == pytest.approx(0.01, abs=1e-6)
    # combo metadata round-trips
    name, leak, strengths = ledger.get_combo(d)
    assert name == "noisy-and" and leak == pytest.approx(0.0)
    assert strengths[p2] == pytest.approx(0.0)
    with pytest.raises(ValueError):
        ledger.set_combo(d, "noisy-xor")


def test_combo_determinism_across_builds(ledger):
    # products commute: parent insertion order must not matter
    import tempfile, shutil
    from ledger import Ledger as L2
    scores = []
    for flip in (False, True):
        dd = tempfile.mkdtemp()
        L = L2(dd)
        d = L.assert_claim("D", 0.5)
        order = [0, 1, 2] if not flip else [2, 1, 0]
        ps = {}
        for i in order:
            ps[i] = L.assert_claim(f"P{i}", 0.9)
        for i in order:
            L.add_support(d, ps[i], "evidential")
        L.set_combo(d, "noisy-and")
        L._revisit(ps[0], {ps[0]: 0.7, ps[1]: 0.8, ps[2]: 0.9})
        scores.append(L._live_claim(d)["score"])
        shutil.rmtree(dd)
    assert scores[0] == pytest.approx(scores[1])


# ----------------------------------------------------------------------
# v0.6: governance (Design Memo 06, Quipu-informed)
# ----------------------------------------------------------------------

def test_writer_tier_default_entrenchment(ledger):
    ledger.register_writer("tristen", "owner")
    ledger.register_writer("agent7", "contributor")
    ledger.register_writer("scraper", "provisional")
    c_owner = ledger.assert_claim("owner claim", 0.6, writer="tristen")
    c_contrib = ledger.assert_claim("contrib claim", 0.6, writer="agent7")
    c_prov = ledger.assert_claim("prov claim", 0.6, writer="scraper")
    c_unknown = ledger.assert_claim("unknown claim", 0.6, writer="mallory")
    c_system = ledger.assert_claim("system claim", 0.6)
    assert ledger.get_entrenchment(c_owner) == pytest.approx(0.75)
    assert ledger.get_entrenchment(c_contrib) == pytest.approx(0.5)
    assert ledger.get_entrenchment(c_prov) == pytest.approx(0.25)
    assert ledger.get_entrenchment(c_unknown) == pytest.approx(0.25)
    assert ledger.get_entrenchment(c_system) == pytest.approx(0.5)
    # explicit entrenchment overrides the tier default
    c_exp = ledger.assert_claim("explicit", 0.6, writer="scraper",
                                entrenchment=0.9)
    assert ledger.get_entrenchment(c_exp) == pytest.approx(0.9)
    # writer recorded and carried across versions
    assert ledger._live_claim(c_owner)["writer"] == "tristen"
    ledger._set_score(c_owner, 0.7, None)
    assert ledger._live_claim(c_owner)["writer"] == "tristen"
    with pytest.raises(ValueError):
        ledger.register_writer("x", "superuser")


def test_contradiction_gate_holds_non_owner_vs_axiomatic(ledger):
    ledger.register_writer("tristen", "owner")
    ledger.register_writer("agent7", "contributor")
    ax = ledger.assert_claim("axiom", 0.99, entrenchment="axiomatic")
    other = ledger.assert_claim("challenger", 0.4, writer="agent7")
    # non-owner vs axiomatic -> held, not queued
    hid = ledger.declare_contradiction(ax, other, writer="agent7")
    assert len(ledger.open_contradictions()) == 0
    held = ledger.held_contradictions()
    assert len(held) == 1 and held[0]["event_id"] == hid
    assert held[0]["payload"]["outcome"] == "held"
    assert held[0]["payload"]["policy"] == "challenge-axiom-requires-owner"
    # resolving a held id explains itself
    r = ledger.resolve_contradiction(hid)
    assert r["resolved"] is False and r["held"] is True
    # owner declaring the same pair enters the queue; hold clears
    oid = ledger.declare_contradiction(ax, other, writer="tristen")
    assert len(ledger.open_contradictions()) == 1
    assert ledger.open_contradictions()[0]["event_id"] == oid
    assert len(ledger.held_contradictions()) == 0


def test_contradiction_gate_passes_non_axiomatic(ledger):
    ledger.register_writer("agent7", "contributor")
    a = ledger.assert_claim("a", 0.8)
    b = ledger.assert_claim("b", 0.2, writer="agent7")
    cid = ledger.declare_contradiction(a, b, writer="agent7")
    assert len(ledger.open_contradictions()) == 1
    assert len(ledger.held_contradictions()) == 0


def test_policies_are_facts_and_bitemporal(ledger):
    p = ledger.audit_policy("challenge-axiom-requires-owner")
    # v0.10: the default policy registers at version 2, rule as data
    assert p is not None and p["version"] == 2
    assert p["rule"]["effect"] == "hold"
    # supersede the policy with an explicit later t; as-of queries see the
    # rule that was in force at T (times relative to actual registration)
    t_init = next(e for e in ledger._events()
                  if e["type"] == "policy_registered")["t"]
    ledger.register_policy("challenge-axiom-requires-owner",
                           "stricter version", version=3)
    assert ledger.audit_policy(
        "challenge-axiom-requires-owner")["version"] == 3
    assert ledger.audit_policy(
        "challenge-axiom-requires-owner", t=t_init)["version"] == 2
    # idempotent re-registration
    n0 = len([e for e in ledger._events()
              if e["type"] == "policy_registered"])
    ledger.register_policy("challenge-axiom-requires-owner",
                           "stricter version", version=3)
    n1 = len([e for e in ledger._events()
              if e["type"] == "policy_registered"])
    assert n0 == n1


# ----------------------------------------------------------------------
# v0.6: automatic contradiction detection
# ----------------------------------------------------------------------

def _opposing_pair(ledger, shared=True):
    s = ledger.assert_claim("shared supporter", 0.9)
    a = ledger.assert_claim("claim A", 0.5)
    b = ledger.assert_claim("claim B", 0.5)
    ledger.add_support(a, s, "evidential", 0.95, 0.05)
    if shared:
        ledger.add_support(b, s, "evidential", 0.05, 0.95)
    else:
        t = ledger.assert_claim("other supporter", 0.9)
        ledger.add_support(b, t, "evidential", 0.05, 0.95)
    return a, b


def test_detect_score_opposition_shared_dependency(ledger):
    a, b = _opposing_pair(ledger, shared=True)
    ledger._set_score(a, 0.95, None)
    ledger._set_score(b, 0.05, None)
    found = ledger.detect_contradictions()
    assert len(found) == 1
    opened = ledger.open_contradictions()
    assert len(opened) == 1
    assert opened[0]["payload"]["auto"] is True
    assert opened[0]["payload"]["signal"] == "score-opposition"
    # idempotent: second run declares nothing new
    assert ledger.detect_contradictions() == []


def test_detect_ignores_unrelated_opposition(ledger):
    a, b = _opposing_pair(ledger, shared=False)
    ledger._set_score(a, 0.95, None)
    ledger._set_score(b, 0.05, None)
    assert ledger.detect_contradictions() == []
    assert ledger.open_contradictions() == []


def test_detect_interval_conflict(ledger):
    a = ledger.assert_claim("interval A", 0.5)
    b = ledger.assert_claim("interval B", 0.5)
    ledger.set_interval(a, 0.9, 0.95)   # strongly true
    ledger.set_interval(b, 0.0, 0.05)   # strongly false
    found = ledger.detect_contradictions()
    assert len(found) == 1
    opened = ledger.open_contradictions()
    assert opened[0]["payload"]["signal"].startswith("interval-conflict")


def test_detect_respects_governance_gate(ledger):
    ledger.register_writer("agent7", "contributor")
    ax = ledger.assert_claim("axiom", 0.99, entrenchment="axiomatic")
    s = ledger.assert_claim("supporter", 0.9)
    ledger.add_support(ax, s, "evidential", 0.95, 0.05)
    c = ledger.assert_claim("challenger", 0.5)
    ledger.add_support(c, s, "evidential", 0.05, 0.95)
    ledger._set_score(c, 0.05, None)
    found = ledger.detect_contradictions()
    assert len(found) == 1
    assert ledger.open_contradictions() == []          # gated...
    assert len(ledger.held_contradictions()) == 1      # ...into the hold


# ----------------------------------------------------------------------
# v0.6: small batch (stability decay, n-ary D-S, abstention, elicitation,
#         kill bars)
# ----------------------------------------------------------------------

def test_stability_decay_for_churn_without_outcomes(ledger):
    from ledger import ENTRENCHMENT_TIERS
    flippy = ledger.assert_claim("flip-flopper", 0.9,
                                 entrenchment="measured")  # 0.75
    steady = ledger.assert_claim("steady", 0.9, entrenchment="measured")
    for i in range(6):
        ledger._set_score(flippy, 0.1 if i % 2 == 0 else 0.9, None)
        ledger._set_score(steady, 0.9, None)
    rep = ledger.learn_entrenchment()
    by_cid = {r["claim_id"]: r for r in rep}
    assert by_cid[flippy]["basis"] == "stability"
    assert by_cid[flippy]["flips"] == 6
    # decay = min(0.5, 6/7) = 0.5 -> 0.75 * 0.5
    assert ledger.get_entrenchment(flippy) == pytest.approx(0.375)
    assert steady not in by_cid  # no flips: untouched
    assert ledger.get_entrenchment(steady) == pytest.approx(0.75)


def test_dempster_combine_ternary():
    from ledger import dempster_combine, interval_to_mass
    A, B, C = frozenset({"A"}), frozenset({"B"}), frozenset({"C"})
    ABC = frozenset({"A", "B", "C"})
    m1 = {A: 0.6, ABC: 0.4}
    m2 = {B: 0.6, ABC: 0.4}
    combined, K = dempster_combine(m1, m2)
    assert K == pytest.approx(0.36)
    assert combined[A] == pytest.approx(0.375)
    assert combined[B] == pytest.approx(0.375)
    assert combined[ABC] == pytest.approx(0.25)
    # binary intervals are the {'T','F'} special case: same K as before
    _, Kb = dempster_combine(interval_to_mass(0.9, 0.95),
                             interval_to_mass(0.0, 0.05))
    assert Kb == pytest.approx(0.9 * 0.95 + 0.05 * 0.0)  # = 0.855
    # total conflict raises instead of producing nonsense
    with pytest.raises(ValueError):
        dempster_combine({A: 1.0}, {B: 1.0})


def test_abstention_policies_caller_owned(ledger):
    import policies
    a = ledger.assert_claim("ignorant claim", 0.5)
    b = ledger.assert_claim("sharp claim", 0.85)
    ledger.set_interval(a, 0.1, 0.9)   # ignorance 0.8
    ledger.set_interval(b, 0.8, 0.9)   # ignorance 0.1
    r1 = policies.ignorance_gated_policy(ledger, a, threshold=0.5)
    r2 = policies.ignorance_gated_policy(ledger, b, threshold=0.5)
    assert r1["action"] == "abstain" and r1["ignorance"] == pytest.approx(0.8)
    assert r2["action"] == "act" and r2["ignorance"] == pytest.approx(0.1)
    r3 = policies.credence_band_policy(ledger, b)
    assert r3["action"] == "act"


def test_elicit_pair_anchors_and_warning(ledger):
    import elicit
    import warnings
    assert elicit.verbal_to_p("very likely") == pytest.approx(0.85)
    p_given, p_not = elicit.elicit_pair("very likely", "unlikely")
    assert (p_given, p_not) == pytest.approx((0.85, 0.30))
    with pytest.raises(KeyError):
        elicit.verbal_to_p("kinda sorta")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        elicit.elicit_pair("unlikely", "very likely")  # counter-evidence
        assert len(w) == 1 and "counter-evidence" in str(w[0].message)


def test_kill_bars_ok_and_breached(ledger):
    rep = ledger.check_kill_bars(trigger_recall=0.96, trigger_precision=0.72)
    assert rep["ok"] is True and rep["breached"] == []
    assert rep["bars"]["brier"] == 0.25
    # pile up unresolved contradictions -> trip the pile-up bar (> 10)
    cs = [ledger.assert_claim(f"c{i}", 0.5) for i in range(24)]
    for i in range(0, 24, 2):
        ledger.declare_contradiction(cs[i], cs[i + 1])
    rep2 = ledger.check_kill_bars()
    breached = {b["criterion"] for b in rep2["breached"]}
    assert "n_open_contradictions" in breached
    assert rep2["ok"] is False
    # None metrics (no outcomes yet) are skipped, not assumed
    assert rep2["values"]["brier"] is None


def test_detect_topic_filter_kills_cross_fact_fps(ledger):
    # two opposed interval claims about DIFFERENT propositions
    a = ledger.assert_claim("claim about X", 0.5)
    b = ledger.assert_claim("claim about Y", 0.5)
    ledger.set_interval(a, 0.9, 0.95)
    ledger.set_interval(b, 0.0, 0.05)
    # filtered first: unrelated topics are not contradictions, nothing queued
    assert ledger.detect_contradictions(topic_of=lambda c: ["X", "Y"][
        0 if c == a else 1]) == []
    assert ledger.open_contradictions() == []
    # same topic: still detected
    assert len(ledger.detect_contradictions(
        topic_of=lambda c: "same")) == 1


def test_detect_unfiltered_interval_low_precision_documented(ledger):
    # documents the known behavior: without a topic filter,
    # interval-conflict flags any opposed decided pair
    a = ledger.assert_claim("claim about X", 0.5)
    b = ledger.assert_claim("claim about Y", 0.5)
    ledger.set_interval(a, 0.9, 0.95)
    ledger.set_interval(b, 0.0, 0.05)
    assert len(ledger.detect_contradictions()) == 1


# ----------------------------------------------------------------------
# v0.7: topics + consolidation pass (Design Memo 08)
# ----------------------------------------------------------------------

def test_topics_bitemporal(ledger):
    a = ledger.assert_claim("some claim", 0.5)
    assert ledger.get_topic(a) is None
    ledger.assign_topic(a, "prop:weather")
    assert ledger.get_topic(a) == "prop:weather"
    ledger.assign_topic(a, "prop:climate")
    assert ledger.get_topic(a) == "prop:climate"
    # detect consumes topics via get_topic
    b = ledger.assert_claim("other claim", 0.5)
    ledger.set_interval(a, 0.9, 0.95)
    ledger.set_interval(b, 0.0, 0.05)
    assert ledger.detect_contradictions(topic_of=ledger.get_topic) == []
    ledger.assign_topic(b, "prop:climate")
    assert len(ledger.detect_contradictions(
        topic_of=ledger.get_topic)) == 1


def test_consolidator_with_fake_llm(ledger):
    import consolidation
    a = ledger.assert_claim("The bridge is safe", 0.9)
    b = ledger.assert_claim("The bridge is unsafe", 0.85)
    c = ledger.assert_claim("The bridge passed inspection", 0.8)
    d = ledger.assert_claim("Bridge deemed safe by inspectors", 0.8)
    reply = ('{"contradicts": [["%s","%s"]], "same": [["%s","%s"]], '
             '"supports": [["%s","%s"]]}' % (a, b, a, d, c, a))
    fake = consolidation.FakeLLM(reply)
    rep = consolidation.Consolidator(ledger, fake).run()
    assert len(rep["contradictions_declared"]) == 1
    assert ledger.open_contradictions()[0]["payload"]["signal"] == \
        "llm-consolidation"
    assert ledger.get_topic(a) == ledger.get_topic(d)
    assert ledger.get_topic(a) == f"prop:{min(a, d)}"
    assert rep["supports_proposed"] == [(c, a)]
    assert rep["cost_usd"] == 0.0
    # unknown ids in a reply are dropped, not crashed on
    bad = consolidation.FakeLLM(
        '{"contradicts": [["NOPE","%s"]], "same": [], "supports": []}' % a)
    rep2 = consolidation.Consolidator(ledger, bad).run()
    assert rep2["contradictions_declared"] == []


def test_parse_relations_robust():
    import consolidation
    text = 'Here you go:\n{"contradicts": [["A","B"]], "same": [], ' \
           '"supports": [["A","A"],["C","D"]]} trailing'
    rel = consolidation.parse_relations(text)
    assert rel["contradicts"] == [("A", "B")]
    assert rel["supports"] == [("C", "D")]  # self-pair dropped
    with pytest.raises(ValueError):
        consolidation.parse_relations("no json here")


# ----------------------------------------------------------------------
# v0.8: conflict-normalized (material) churn (Design Memo 09)
# ----------------------------------------------------------------------

def test_material_churn_absorbs_jitter(ledger):
    jitter = ledger.assert_claim("jitter claim", 0.5)
    for i in range(10):
        ledger.manual_score(jitter, 0.51 if i % 2 == 0 else 0.49)
    d = ledger.kill_metrics()["churn_detail"][jitter]
    assert d["raw"] >= 8                 # raw churn screams
    assert d["material_moves"] == 0      # ...about nothing material
    assert d["material_churn"] == 0


def test_material_churn_catches_oscillation(ledger):
    osc = ledger.assert_claim("oscillating claim", 0.5)
    for i in range(10):
        ledger.manual_score(osc, 0.7 if i % 2 == 0 else 0.3)
    d = ledger.kill_metrics()["churn_detail"][osc]
    assert d["material_moves"] == 10
    assert d["material_churn"] == 9
    res = ledger.check_kill_bars()
    assert res["values"]["max_material_churn"] == 9
    assert any(b["criterion"] == "max_material_churn"
               for b in res["breached"])


def test_material_churn_counts_real_reversal_once(ledger):
    c = ledger.assert_claim("contested claim", 0.5)
    # sub-materiality tugs, then a genuine move up, then a genuine
    # move back down: exactly one material reversal
    for s in (0.53, 0.50, 0.53, 0.56, 0.53, 0.50):
        ledger.manual_score(c, s)
    d = ledger.kill_metrics()["churn_detail"][c]
    assert d["material_moves"] == 2
    assert d["material_churn"] == 1
    assert d["conflict_balance"] > 0.5


def test_churn_detail_one_directional(ledger):
    c = ledger.assert_claim("steady claim", 0.1)
    for s in (0.2, 0.3, 0.4, 0.5):
        ledger.manual_score(c, s)
    d = ledger.kill_metrics()["churn_detail"][c]
    assert d["raw"] == 0 and d["material_churn"] == 0
    assert d["conflict_balance"] == 0.0


# ----------------------------------------------------------------------
# v0.9: ed25519 vectors, escalation, signed verdicts (Design Memo 10)
# ----------------------------------------------------------------------

import ed25519 as _ed

_RFC_VECTORS = [
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
     "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
     "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
     "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
     "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
     "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


def test_ed25519_rfc8032_vectors():
    for sk, pk, msg, sig in _RFC_VECTORS:
        sk_b, pk_b = bytes.fromhex(sk), bytes.fromhex(pk)
        msg_b, sig_b = bytes.fromhex(msg), bytes.fromhex(sig)
        assert _ed.publickey(sk_b) == pk_b
        assert _ed.sign(sk_b, msg_b) == sig_b  # deterministic
        assert _ed.verify(pk_b, msg_b, sig_b)
        bad = bytearray(sig_b)
        bad[0] ^= 1
        assert not _ed.verify(pk_b, msg_b, bytes(bad))


_OWNER_SEED = bytes(range(32))


def _governed(ledger, keyed=True):
    """Axiom + challenger + a held contradiction. Returns (held_id,)."""
    ledger.register_writer("owner-1", "owner",
                           public_key=(_ed.publickey(_OWNER_SEED).hex()
                                       if keyed else None))
    ledger.register_writer("contrib-1", "contributor")
    axiom = ledger.assert_claim("the axiom", 0.9, entrenchment=1.0)
    chal = ledger.assert_claim("the challenger", 0.8, entrenchment=0.5)
    held_id = ledger.declare_contradiction(
        axiom, chal, p_loser_given_winner=0.11, writer="contrib-1")
    assert len(ledger.held_contradictions()) == 1
    return held_id, axiom, chal


def _sign(msg):
    return _ed.sign(_OWNER_SEED, msg.encode()).hex()


def test_escalation_release_flow(ledger):
    held_id, axiom, chal = _governed(ledger, keyed=False)
    out = ledger.escalate_contradiction(held_id, "release",
                                        writer="owner-1")
    assert out["decision"] == "release"
    assert ledger.held_contradictions() == []
    open_cs = ledger.open_contradictions()
    assert [e["event_id"] for e in open_cs] == [out["contradiction_id"]]
    # challenger's elicited cross-likelihood survived the hold
    assert open_cs[0]["payload"]["p_loser_given_winner"] == 0.11
    # and the released contradiction resolves normally
    res = ledger.resolve_contradiction(out["contradiction_id"])
    assert res["resolved"] and res["loser"] == chal


def test_escalation_dismiss_flow(ledger):
    held_id, _, _ = _governed(ledger, keyed=False)
    out = ledger.escalate_contradiction(held_id, "dismiss",
                                        writer="owner-1")
    assert out["decision"] == "dismiss"
    assert ledger.held_contradictions() == []
    assert ledger.open_contradictions() == []
    with pytest.raises(KeyError):  # no longer held: no double verdict
        ledger.escalate_contradiction(held_id, "dismiss",
                                      writer="owner-1")


def test_escalation_requires_owner(ledger):
    held_id, _, _ = _governed(ledger)
    with pytest.raises(PermissionError):
        ledger.escalate_contradiction(held_id, "release",
                                      writer="contrib-1")
    with pytest.raises(PermissionError):
        ledger.escalate_contradiction(held_id, "release", writer=None)
    with pytest.raises(KeyError):
        ledger.escalate_contradiction("E-nope", "release",
                                      writer="owner-1")


def test_keyed_owner_must_sign_escalation(ledger):
    held_id, _, _ = _governed(ledger, keyed=True)
    with pytest.raises(PermissionError):  # missing signature
        ledger.escalate_contradiction(held_id, "release",
                                      writer="owner-1")
    msg = ledger.verdict_message("escalate", held_id, "owner-1", "dismiss")
    with pytest.raises(PermissionError):  # signature for wrong decision
        ledger.escalate_contradiction(held_id, "release",
                                      writer="owner-1", signature=_sign(msg))
    msg = ledger.verdict_message("escalate", held_id, "owner-1", "release")
    out = ledger.escalate_contradiction(held_id, "release",
                                        writer="owner-1",
                                        signature=_sign(msg))
    assert out["decision"] == "release"
    audit = ledger.verify_verdict_signatures()
    assert audit == {"checked": 1, "valid": 1, "invalid": []}


def test_keyed_writer_must_sign_resolution(ledger):
    ledger.register_writer(
        "owner-1", "owner",
        public_key=_ed.publickey(_OWNER_SEED).hex())
    a = ledger.assert_claim("claim a", 0.9, entrenchment=0.75)
    b = ledger.assert_claim("claim b", 0.8, entrenchment=0.25)
    cid = ledger.declare_contradiction(a, b, writer="owner-1")
    with pytest.raises(PermissionError):
        ledger.resolve_contradiction(cid, writer="owner-1")
    msg = ledger.verdict_message("resolve", cid, "owner-1")
    res = ledger.resolve_contradiction(cid, writer="owner-1",
                                       signature=_sign(msg))
    assert res["resolved"] and res["loser"] == b
    audit = ledger.verify_verdict_signatures()
    assert audit["checked"] == 1 and audit["valid"] == 1
    # unkeyed writers are untouched by the rule (back-compat)
    a2 = ledger.assert_claim("claim a2", 0.9, entrenchment=0.75)
    b2 = ledger.assert_claim("claim b2", 0.8, entrenchment=0.25)
    cid2 = ledger.declare_contradiction(a2, b2, writer="contrib-x")
    assert ledger.resolve_contradiction(
        cid2, writer="contrib-x")["resolved"]


def test_signature_audit_detects_key_rotation(ledger):
    held_id, _, _ = _governed(ledger, keyed=True)
    msg = ledger.verdict_message("escalate", held_id, "owner-1", "dismiss")
    ledger.escalate_contradiction(held_id, "dismiss", writer="owner-1",
                                  signature=_sign(msg))
    assert ledger.verify_verdict_signatures()["valid"] == 1
    other = _ed.publickey(bytes(range(32, 64))).hex()
    ledger.register_writer("owner-1", "owner", public_key=other)
    audit = ledger.verify_verdict_signatures()
    assert audit["valid"] == 0 and len(audit["invalid"]) == 1
    # re-registering without a key preserves it (no silent strip)
    ledger.register_writer("owner-1", "owner")
    assert ledger.get_writer_pubkey("owner-1") == other


# ----------------------------------------------------------------------
# v0.10: named-graph partitions + predicate policies (Design Memo 11)
# ----------------------------------------------------------------------

import ledger as ledger_module

def test_graph_assignment_and_ceilings(ledger):
    ledger.register_graph("quarantine", 0.25)
    assert ledger.get_graph_ceiling("quarantine") == 0.25
    assert ledger.get_graph_ceiling("public") == 1.0
    c = ledger.assert_claim("a claim", 0.9, entrenchment=0.75)
    assert ledger.get_graph(c) == "public"
    assert ledger.effective_entrenchment(c) == 0.75
    ledger.assign_graph(c, "quarantine")
    assert ledger.get_graph(c) == "quarantine"
    assert ledger.effective_entrenchment(c) == 0.25
    # stored value is never rewritten by the cap
    assert float(ledger._live_claim(c)["entrenchment"]) == 0.75
    with pytest.raises(KeyError):
        ledger.assign_graph(c, "no-such-graph")
    with pytest.raises(KeyError):
        ledger.assign_graph("C-nope", "quarantine")
    with pytest.raises(ValueError):
        ledger.register_graph("bad", 1.5)


def test_graph_ceiling_is_bitemporal(ledger):
    ledger.register_graph("lab", 0.5, t="2026-01-01T00:00:00+00:00")
    ledger.register_graph("lab", 0.3, t="2026-06-01T00:00:00+00:00")
    assert ledger.audit_graph("lab")["ceiling"] == 0.3
    assert ledger.audit_graph(
        "lab", t="2026-03-01T00:00:00+00:00")["ceiling"] == 0.5


def test_cross_graph_composition_never_widens(ledger):
    ledger.register_graph("quarantine", 0.25)
    parent = ledger.assert_claim("tainted parent", 0.9, entrenchment=0.5)
    ledger.assign_graph(parent, "quarantine")
    child = ledger.assert_claim("derived", 0.9, entrenchment=0.9)
    assert ledger.effective_entrenchment(child) == 0.9
    ledger.add_support(child, parent, "evidential", 0.9, 0.1)
    # resting on a quarantined claim caps the child's authority
    assert ledger.effective_entrenchment(child) == 0.25
    ledger.retract_support(child, parent)
    assert ledger.effective_entrenchment(child) == 0.9  # cap lifts


def test_quarantine_strips_axiom_protection_and_wins_resolution(ledger):
    ledger.register_graph("quarantine", 0.25)
    ledger.register_writer("contrib-1", "contributor")
    axiom = ledger.assert_claim("stored axiom", 0.9, entrenchment=1.0)
    ledger.assign_graph(axiom, "quarantine")
    other = ledger.assert_claim("ordinary", 0.8, entrenchment=0.5)
    # stored 1.0 but effective 0.25: no hold for a non-owner challenge
    cid = ledger.declare_contradiction(axiom, other, writer="contrib-1")
    assert [e["event_id"] for e in ledger.open_contradictions()] == [cid]
    # and in resolution the capped "axiom" is the loser
    res = ledger.resolve_contradiction(cid)
    assert res["resolved"] and res["loser"] == axiom


def test_default_policy_rule_is_data(ledger):
    p = ledger.audit_policy("challenge-axiom-requires-owner")
    assert p["rule"] == ledger_module.DEFAULT_POLICY_RULE
    # and it still holds a non-owner challenge to a true (public) axiom
    ledger.register_writer("contrib-1", "contributor")
    axiom = ledger.assert_claim("real axiom", 0.9, entrenchment=1.0)
    chal = ledger.assert_claim("challenger", 0.8, entrenchment=0.5)
    held_id = ledger.declare_contradiction(axiom, chal,
                                           writer="contrib-1")
    held = ledger.held_contradictions()
    assert [e["event_id"] for e in held] == [held_id]
    assert held[0]["payload"]["policy"] == (
        "challenge-axiom-requires-owner")


def test_predicate_policy_denies_resolution(ledger):
    ledger.register_policy(
        "no-easy-resolutions", "deny resolving away strong claims",
        version=1,
        rule={"action": "resolve_contradiction", "effect": "deny",
              "when": {"field": "loser_entrenchment", "op": ">=",
                       "value": 0.75}})
    strong = ledger.assert_claim("strong", 0.9, entrenchment=0.9)
    mid = ledger.assert_claim("mid", 0.8, entrenchment=0.75)
    cid = ledger.declare_contradiction(strong, mid)
    with pytest.raises(PermissionError):
        ledger.resolve_contradiction(cid)
    assert any(e["type"] == "policy_denied"
               for e in ledger._events())
    assert [e["event_id"] for e in ledger.open_contradictions()] == [cid]
    # a resolution whose loser is weak proceeds
    weak = ledger.assert_claim("weak", 0.7, entrenchment=0.25)
    cid2 = ledger.declare_contradiction(strong, weak)
    assert ledger.resolve_contradiction(cid2)["resolved"]


def test_predicate_language_composition_and_validation(ledger):
    # any/not nesting, evaluated through an escalate-deny rule
    ledger.register_policy(
        "no-dismissals", "owners may release but never dismiss",
        version=1,
        rule={"action": "escalate_contradiction", "effect": "deny",
              "when": {"any": [
                  {"field": "decision", "op": "==", "value": "dismiss"},
                  {"not": {"field": "writer_tier", "op": "==",
                           "value": "owner"}}]}})
    held_id, _, _ = _governed(ledger, keyed=False)
    with pytest.raises(PermissionError):
        ledger.escalate_contradiction(held_id, "dismiss",
                                      writer="owner-1")
    out = ledger.escalate_contradiction(held_id, "release",
                                        writer="owner-1")
    assert out["decision"] == "release"
    # malformed rules are refused at registration
    with pytest.raises(ValueError):
        ledger.register_policy(
            "junk", "bad op", version=1,
            rule={"action": "resolve_contradiction", "effect": "deny",
                  "when": {"field": "x", "op": "~=", "value": 1}})
    with pytest.raises(ValueError):  # hold needs a verdict queue
        ledger.register_policy(
            "junk2", "hold on resolve", version=1,
            rule={"action": "resolve_contradiction", "effect": "hold",
                  "when": {"field": "x", "op": "==", "value": 1}})


# ------------------------------------------------------------------
# v0.11 hardening (DESIGN-12): writer lock + store verification
# ------------------------------------------------------------------

def test_writer_lock_excludes_second_opener(tmp_path):
    d = str(tmp_path / "led")
    first = Ledger(d)
    try:
        with pytest.raises(RuntimeError):
            Ledger(d)
    finally:
        first.close()
    second = Ledger(d)  # lock released by close()
    second.close()


def test_verify_store_clean(ledger):
    c = ledger.assert_claim("verified claim", 0.5)
    ledger._set_score(c, 0.8, None, actor="agent")
    rep = ledger.verify_store()
    assert rep["ok"] and rep["problems"] == []
    assert rep["claims_checked"] >= 1


def test_verify_store_detects_projection_tamper(ledger):
    c = ledger.assert_claim("tamper target", 0.5)
    ledger.db.execute(
        "UPDATE claims SET score = 0.99 WHERE claim_id = ? "
        "AND txn_to IS NULL", (c,))
    ledger.db.commit()
    rep = ledger.verify_store()
    assert not rep["ok"]
    assert any(c in p for p in rep["problems"])


def test_verify_store_detects_log_corruption(ledger, tmp_path):
    ledger.assert_claim("log target", 0.5)
    with open(ledger.log_path, "a", encoding="utf-8") as f:
        f.write("{not json\n")
    rep = ledger.verify_store()
    assert not rep["ok"]
    assert any("unparseable" in p for p in rep["problems"])


def test_kill_metrics_tolerates_mixed_t_types(ledger):
    # Regression (OVERRIDE-CAL-01): a step-clocked (int t) revision
    # history plus a wall-clock (ISO string t) human manual_score used
    # to crash kill_metrics at hist.sort() — int vs str comparison.
    cid = ledger.assert_claim("mixed clock claim", 0.5)
    ledger._set_score(cid, 0.7, None, t=3)
    ledger.manual_score(cid, 0.2)  # default t: ISO string
    km = ledger.kill_metrics()
    assert km["n_manual_overrides"] == 1
    assert km["override_rate"] is not None and km["override_rate"] > 0


def test_manual_score_propagates_to_dependents(ledger):
    # v0.11.1: a human correction re-derives dependents, like evidence.
    fact = ledger.assert_claim("propagation fact", 0.5)
    dep = ledger.assert_claim("propagation dependent", 0.5)
    ledger.add_support(dep, fact, "evidential", p_given=0.9,
                       p_given_not=0.1)
    before = ledger.get_score(dep)
    ledger.manual_score(fact, 0.95)
    after = ledger.get_score(dep)
    assert after > before + 0.05
