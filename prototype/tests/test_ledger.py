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
    assert p is not None and p["version"] == 1
    # supersede the policy with an explicit later t; as-of queries see the
    # rule that was in force at T (times relative to actual registration)
    t_init = next(e for e in ledger._events()
                  if e["type"] == "policy_registered")["t"]
    ledger.register_policy("challenge-axiom-requires-owner",
                           "stricter version", version=2)
    assert ledger.audit_policy(
        "challenge-axiom-requires-owner")["version"] == 2
    assert ledger.audit_policy(
        "challenge-axiom-requires-owner", t=t_init)["version"] == 1
    # idempotent re-registration
    n0 = len([e for e in ledger._events()
              if e["type"] == "policy_registered"])
    ledger.register_policy("challenge-axiom-requires-owner",
                           "stricter version", version=2)
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
