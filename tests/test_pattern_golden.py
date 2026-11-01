"""DESIGN-17 stage 5: pre-registered engine expectations (P6).

The expected values below are derived from the documented
rules, not captured from the implementation:

- A claim supported evidentially with p_given 0.9 and
  p_given_not 0.2 settles by the Jeffrey rule when its
  supporter is revised: supporter at 1.0 settles it to
  0.9*1.0 + 0.2*0.0 = 0.9 exactly; supporter at 0.0
  settles it to 0.9*0.0 + 0.2*1.0 = 0.2 exactly.
- Structural impact of the supporter is exactly the
  supported claim, at distance 1, one path.
- verify_store reports ok with both claims checked.
- The generated matrix's confidence for the supported
  claim equals the engine's settled score at each step:
  the engine and the generated layer are pinned to each
  other.
"""

from epistemic_ledger.ledger import Ledger
from epistemic_ledger.pattern import matrix_from_ledger

T = "2026-06-01T00:00:00+00:00"


def test_engine_reproduces_preregistered_expectations(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    supporter = led.assert_claim("the supporter", 0.5, t=T)
    supported = led.assert_claim("the supported", 0.5, t=T)
    led.add_support(
        supported, supporter, "evidential", p_given=0.9, p_given_not=0.2, t=T
    )

    led.manual_score(supporter, 1.0)
    assert led.get_score(supported) == 0.9
    rows = {r["claim_id"]: r for r in matrix_from_ledger(led)["claims"]}
    assert rows[supported]["confidence"] == 0.9

    led.manual_score(supporter, 0.0)
    assert led.get_score(supported) == 0.2
    rows = {r["claim_id"]: r for r in matrix_from_ledger(led)["claims"]}
    assert rows[supported]["confidence"] == 0.2

    impact = led.impact(supporter)
    assert impact["mode"] == "structural"
    assert [n["id"] for n in impact["nodes"]] == [supported]
    assert impact["nodes"][0]["distance"] == 1
    assert impact["nodes"][0]["path_count"] == 1

    check = led.verify_store()
    assert check["ok"] is True
    assert check["claims_checked"] == 2
    led.close()
