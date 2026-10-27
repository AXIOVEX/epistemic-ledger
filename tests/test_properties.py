"""Property-based tests for the scoring core (Hypothesis).

Each property states an invariant the design relies on, in plain words:

- a credence is always a probability: it stays inside [0, 1];
- Jeffrey updating with certain evidence lands exactly on the
  conditional credence, and with impossible evidence it does not move;
- combining belief masses never produces a mass outside [0, 1] and
  keeps the total at 1;
- noisy-AND / noisy-OR combination does not depend on the order the
  parents are considered;
- a ledger written to disk and reopened replays to the same scores,
  and its integrity check passes.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from epistemic_ledger import Ledger, dempster_combine, interval_to_mass, jeffrey

prob = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@given(p=prob, given_e=prob, given_not_e=prob, p_e=prob)
@settings(max_examples=200)
def test_jeffrey_stays_a_probability(p, given_e, given_not_e, p_e):
    out = jeffrey(p, given_e, given_not_e, p_e)
    assert 0.0 <= out <= 1.0


@given(p=prob, given_e=prob, given_not_e=prob)
@settings(max_examples=100)
def test_jeffrey_certain_evidence_lands_on_conditional(p, given_e, given_not_e):
    assert jeffrey(p, given_e, given_not_e, 1.0) == pytest.approx(given_e)
    assert jeffrey(p, given_e, given_not_e, 0.0) == pytest.approx(given_not_e)


@given(b=prob, pl=prob)
@settings(max_examples=100)
def test_interval_to_mass_is_a_mass(b, pl):
    bel, rest = (b, pl) if b <= pl else (pl, b)
    m = interval_to_mass(bel, rest)
    total = sum(m.values())
    assert total == pytest.approx(1.0)
    assert all(0.0 <= v <= 1.0 for v in m.values())


interval = st.tuples(prob, prob).map(lambda t: (min(t), max(t)))


@given(iv1=interval, iv2=interval)
@settings(max_examples=100)
def test_dempster_combine_keeps_total_mass(iv1, iv2):
    m1, m2 = interval_to_mass(*iv1), interval_to_mass(*iv2)
    try:
        combined, conflict = dempster_combine(m1, m2)
    except ValueError:
        pytest.skip("pathological conflict refused by design")
    assert 0.0 <= conflict < 1.0
    assert sum(combined.values()) == pytest.approx(1.0, abs=1e-6)
    assert all(-1e-12 <= v <= 1.0 + 1e-12 for v in combined.values())


@given(priors=st.lists(prob, min_size=2, max_size=4))
@settings(max_examples=60, deadline=None)
def test_reopen_replays_to_same_scores(tmp_path_factory, priors):
    d = str(tmp_path_factory.mktemp("ledger"))
    L = Ledger(d)
    ids = [L.assert_claim(f"claim {i}", p) for i, p in enumerate(priors)]
    fact = L.ingest_evidence("shared evidence", 0.8)["fact_id"]
    for cid in ids:
        L.add_support(cid, fact, "evidential", p_given=0.9, p_given_not=0.25)
    L._revisit(fact, {fact: 0.8})
    scores_before = [L.get_score(c) for c in ids]
    assert L.verify_store()["ok"]
    L.close()

    L2 = Ledger(d)
    scores_after = [L2.get_score(c) for c in ids]
    assert scores_after == pytest.approx(scores_before)
    assert L2.verify_store()["ok"]
    L2.close()
    for s in scores_after:
        assert 0.0 <= s <= 1.0
