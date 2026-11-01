"""DESIGN-17 stage 3: the generated claims matrix (P3).

The matrix is a pure function of the ledger's records:
regeneration from the same ledger is byte-identical, every
live and terminal claim appears exactly once, and every row
traces to a claim asserted in the ledger.
"""

import json

from epistemic_ledger.ledger import Ledger
from epistemic_ledger.pattern import (
    build_matrix,
    matrix_from_ledger,
    matrix_json,
    matrix_markdown,
)

T1 = "2026-06-01T00:00:00+00:00"
T2 = "2026-06-02T00:00:00+00:00"
T3 = "2026-06-03T00:00:00+00:00"


def _ledger(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    a = led.assert_claim(
        "the soak is stable",
        0.8,
        source="nightly run 5",
        falsifier="a soak report with errors",
        does_not_establish="power-loss durability",
        t=T1,
    )
    b = led.assert_claim("the bench clears 2000/s", 0.6, t=T1)
    led.manual_score(a, 0.65)
    c = led.supersede(
        b,
        "the bench clears 2000/s on a quiet runner",
        0.7,
        reason="the first wording hid the condition",
        source="tier run 4",
        t=T2,
    )
    d = led.assert_claim("a retracted claim", 0.4, t=T2)
    led.set_claim_status(d, "dead", reason="moot", source="review", t=T3)
    led.close()
    return a, b, c, d


def test_matrix_is_complete_and_traces(tmp_path):
    a, b, c, d = _ledger(tmp_path)
    led = Ledger(str(tmp_path / "store"))
    matrix = matrix_from_ledger(led)
    rows = {r["claim_id"]: r for r in matrix["claims"]}
    # Every claim exactly once — live and terminal alike.
    assert set(rows) == {a, b, c, d}
    assert len(matrix["claims"]) == 4
    # Assertion order is the log's order.
    assert [r["claim_id"] for r in matrix["claims"]] == [a, b, c, d]
    # Field fidelity against the pattern fields.
    assert rows[a]["statement"] == "the soak is stable"
    assert rows[a]["source"] == "nightly run 5"
    assert rows[a]["date"] == T1
    assert rows[a]["falsifier"] == "a soak report with errors"
    assert rows[a]["does_not_establish"] == "power-loss durability"
    # Confidence is the SETTLED score, not the prior.
    assert rows[a]["confidence"] == 0.65
    assert rows[a]["status"] == "active"
    # The reclassification shows as status + linkage.
    assert rows[b]["status"] == "superseded"
    assert rows[b]["superseded_by"] == c
    assert rows[c]["status"] == "active"
    assert rows[c]["source"] == "tier run 4"
    assert rows[d]["status"] == "dead"
    assert matrix["counts"] == {"active": 2, "superseded": 1, "dead": 1}
    led.close()


def test_matrix_matches_live_projection(tmp_path):
    a, b, c, d = _ledger(tmp_path)
    led = Ledger(str(tmp_path / "store"))
    matrix = matrix_from_ledger(led)
    rows = {r["claim_id"]: r for r in matrix["claims"]}
    for claim in led.list_claims():
        row = rows[claim["claim_id"]]
        assert row["confidence"] == claim["score"]
        assert row["statement"] == claim["statement"]
        assert row["source"] == claim["source"]
        assert row["falsifier"] == claim["falsifier"]
        assert row["does_not_establish"] == claim["does_not_establish"]
    led.close()


def test_matrix_regeneration_is_byte_identical(tmp_path):
    _ledger(tmp_path)
    led = Ledger(str(tmp_path / "store"))
    events = led._events()
    first = matrix_json(build_matrix(events))
    second = matrix_json(build_matrix(events))
    assert first == second
    assert json.loads(first)["format"] == "epistemic-ledger-matrix/1"
    md = matrix_markdown(build_matrix(events))
    assert md == matrix_markdown(build_matrix(events))
    assert "generated — do not edit" in md
    assert "the soak is stable" in md
    led.close()
