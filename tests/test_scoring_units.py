"""Focused unit tests for pieces the ported suite touches only lightly:
elicitation, abstention policies, version reporting, and the public
package surface."""

import pytest

from epistemic_ledger import __version__
from epistemic_ledger.elicit import elicit_pair, verbal_to_p
from epistemic_ledger.ledger import Ledger
from epistemic_ledger.policies import credence_band_policy, ignorance_gated_policy


def test_version_is_a_string():
    assert isinstance(__version__, str) and __version__


def test_verbal_scale_orders_correctly():
    words = [
        "almost impossible",
        "very unlikely",
        "unlikely",
        "toss-up",
        "likely",
        "very likely",
        "almost certain",
    ]
    values = [verbal_to_p(w) for w in words]
    assert values == sorted(values)
    assert values[0] == pytest.approx(0.05)
    assert values[-1] == pytest.approx(0.95)


def test_elicit_pair_rejects_unknown_words():
    with pytest.raises((ValueError, KeyError)):
        elicit_pair("maybe-ish", "likely")


def test_policies_on_a_live_ledger(tmp_path):
    L = Ledger(str(tmp_path / "l"))
    sure = L.assert_claim("well supported", 0.9)
    vague = L.assert_claim("barely supported", 0.5)
    L.set_interval(vague, 0.1, 0.95)  # wide interval: high ignorance
    assert credence_band_policy(L, sure)["action"] == "act"
    gated = ignorance_gated_policy(L, vague, threshold=0.3)
    assert gated["action"] == "abstain"  # ignorance 0.85 > threshold 0.3
    assert gated["ignorance"] == pytest.approx(0.85)
    L.close()
