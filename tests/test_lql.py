"""LQL — the Ledger Query Language (DESIGN-13 section 5).

Claim Q1: for every construct, the LQL result equals the
corresponding core API result on the same store.
Claim Q2: malformed input fails with a parse error naming the
position and executes nothing — fuzzed mutations of valid queries
produce only parse errors or valid results, never a panic, and
the store's bytes are unchanged across the fuzz run (LQL cannot
write at all).
"""

import hashlib
import os
import random

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from epistemic_ledger import Ledger
from epistemic_ledger.cli import main as cli_main
from epistemic_ledger.lql import LQLParseError, parse


def _store(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    a = led.assert_claim("alpha", 0.9, writer="amy")
    b = led.assert_claim("beta", 0.4)
    c = led.assert_claim("gamma", 0.7, critical=True)
    led.register_writer("amy", "owner")
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    did = led.record_decision("ship decision", [b])
    return led, a, b, c, did


# ------------------------------------------------------------------
# constructs
# ------------------------------------------------------------------


def test_claim_and_claims(tmp_path):
    led, a, b, c, _ = _store(tmp_path)
    got = led.query(f"CLAIM {a}")
    assert got == led.get_claim(a)  # Q1: exactly the core API result
    assert got["statement"] == "alpha"
    assert led.query("CLAIM Cmissing") is None
    all_claims = led.query("CLAIMS")
    assert {r["claim_id"] for r in all_claims} == {a, b, c}
    rich = led.query("CLAIMS WHERE score > 0.5")
    assert {r["claim_id"] for r in rich} == {a, c}
    combo = led.query("CLAIMS WHERE score >= 0.4 AND writer = 'amy'")
    assert [r["claim_id"] for r in combo] == [a]
    either = led.query("CLAIMS WHERE score < 0.5 OR critical = true")
    assert {r["claim_id"] for r in either} == {b, c}
    led.close()


def test_why_depends_impact_equal_core_api(tmp_path):
    led, a, b, c, _ = _store(tmp_path)
    assert led.query(f"WHY {b}") == led.why(b)
    assert led.query(f"DEPENDS {a}") == led.depends_on(a)
    assert led.query(f"IMPACT {a}") == led.impact(a)
    prop = led.query(f"IMPACT {a} PROPAGATED TO 0.1")
    assert prop == led.impact(a, mode="propagated", revised_score=0.1)
    led.close()


def test_events_decisions_health(tmp_path):
    led, a, b, c, did = _store(tmp_path)
    asserts = led.query("EVENTS WHERE type = 'assert'")
    assert len(asserts) == 3
    assert all(e["type"] == "assert" for e in asserts)
    decs = led.query("DECISIONS WHERE kind = 'decision'")
    assert [d["decision_id"] for d in decs] == [did]
    assert led.query("HEALTH") == led.health()
    led.close()


def test_as_of(tmp_path):
    led = Ledger(str(tmp_path / "store"))
    a = led.assert_claim("alpha", 0.9, t="2026-01-01T00:00:00+00:00")
    led.manual_score(a, 0.3, t="2026-02-01T00:00:00+00:00")
    early = led.query("AS_OF 2026-01-15T00:00:00+00:00 CLAIM " + a)
    assert early["score"] == 0.9
    late = led.query("AS_OF 2026-03-01T00:00:00+00:00 CLAIM " + a)
    assert late["score"] == 0.3
    events = led.query("AS_OF 2026-01-15T00:00:00+00:00 EVENTS")
    assert all(e["t"] <= "2026-01-15T00:00:00+00:00" for e in events)
    with pytest.raises(LQLParseError):
        led.query("AS_OF 2026-01-15T00:00:00+00:00 WHY " + a)
    led.close()


# ------------------------------------------------------------------
# parse errors carry positions and execute nothing
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "SELECT * FROM claims",
        "CLAIM",
        "CLAIMS WHERE score >> 0.5",
        "CLAIMS WHERE bogus = 1",
        "CLAIMS WHERE score = 'high'",
        "CLAIMS WHERE score > 0.5 AND",
        "IMPACT C1 PROPAGATED TO 'zero'",
        "CLAIMS WHERE writer = 'unterminated",
        "HEALTH now",
        "AS_OF not-a-time CLAIMS",
        "AS_OF 2026-01-15T00:00:00+00:00 IMPACT C1",
    ],
)
def test_parse_errors(tmp_path, text):
    led, *_ = _store(tmp_path)
    with pytest.raises(LQLParseError) as exc_info:
        led.query(text)
    assert exc_info.value.position >= 0
    assert "position" in str(exc_info.value)
    led.close()


def test_parse_is_pure():
    plan = parse("CLAIMS WHERE score > 0.5 AND writer = 'amy' OR kind = 'credence'")
    assert plan["kind"] == "claims"
    assert plan["filter"][0] == "or"  # AND bound tighter: (a AND b) OR c
    assert plan["filter"][1][0] == "and"


# ------------------------------------------------------------------
# Q2 fuzz: mutations yield parse errors or valid results, no writes
# ------------------------------------------------------------------


def _store_bytes(led):
    out = {}
    for name in ("events.jsonl", "ledger.db"):
        with open(os.path.join(led.path, name), "rb") as f:
            out[name] = hashlib.sha256(f.read()).hexdigest()
    return out


def test_q2_fuzz_never_writes_never_panics(tmp_path):
    led, a, b, c, did = _store(tmp_path)
    corpus = [
        f"CLAIM {a}",
        "CLAIMS WHERE score > 0.5",
        f"WHY {b}",
        f"IMPACT {a} PROPAGATED TO 0.25",
        "EVENTS WHERE type = 'assert'",
        "DECISIONS",
        "HEALTH",
        "AS_OF 2026-01-15T00:00:00+00:00 CLAIMS WHERE score >= 0.1",
    ]
    before = _store_bytes(led)
    rng = random.Random(20261028)
    alphabet = "ABCDEXYZ'=<>! 0123456789'\""
    outcomes = {"ok": 0, "parse_error": 0}
    for _ in range(400):
        text = rng.choice(corpus)
        for _ in range(rng.randint(1, 3)):
            if not text:
                break
            pos = rng.randrange(len(text))
            mutation = rng.randrange(3)
            if mutation == 0:
                text = text[:pos] + text[pos + 1 :]
            elif mutation == 1:
                text = text[:pos] + rng.choice(alphabet) + text[pos:]
            else:
                text = text[:pos] + rng.choice(alphabet) + text[pos + 1 :]
        try:
            led.query(text)
            outcomes["ok"] += 1
        except LQLParseError:
            outcomes["parse_error"] += 1
        except KeyError:
            # A well-formed query naming a claim the mutations
            # invented: a clean domain error, not a panic.
            outcomes["ok"] += 1
        # any other exception type propagates and fails the test
    assert outcomes["parse_error"] > 50  # the fuzz really mutates
    assert _store_bytes(led) == before
    led.close()


# ------------------------------------------------------------------
# Q1 property: LQL equals the core API on randomized stores
# ------------------------------------------------------------------


@settings(max_examples=25, deadline=None)
@given(
    n=st.integers(min_value=2, max_value=7),
    priors=st.lists(st.floats(min_value=0.05, max_value=0.95), min_size=7, max_size=7),
    threshold=st.floats(min_value=0.0, max_value=1.0),
)
def test_q1_lql_matches_core_api(n, priors, threshold):
    import shutil
    import tempfile

    tmp = tempfile.mkdtemp(prefix="epistemic-ledger-q1-")
    try:
        led = Ledger(os.path.join(tmp, "store"))
        ids = [led.assert_claim(f"s{i}", priors[i]) for i in range(n)]
        for i in range(1, n):
            led.add_support(
                ids[i], ids[i - 1], "evidential", p_given=0.9, p_given_not=0.2
            )
        root = ids[0]
        assert led.query(f"WHY {ids[-1]}") == led.why(ids[-1])
        assert led.query(f"DEPENDS {root}") == led.depends_on(root)
        assert led.query(f"IMPACT {root}") == led.impact(root)
        via_lql = led.query(f"CLAIMS WHERE score > {threshold!r}")
        via_api = [
            c
            for c in (led.query(f"CLAIM {cid}") for cid in ids)
            if c is not None and c["score"] > threshold
        ]
        assert {c["claim_id"] for c in via_lql} == {c["claim_id"] for c in via_api}
        assert led.query("HEALTH") == led.health()
        assert led.query(f"CLAIM {root}")["score"] == led.get_score(root)
        led.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------
# CLI faces for the same constructs
# ------------------------------------------------------------------


def test_cli_impact_query_health(tmp_path, capsys):
    led, a, b, c, did = _store(tmp_path)
    path = led.path
    led.close()
    assert cli_main(["health", path]) == 0
    health_out = capsys.readouterr().out
    assert '"ok": true' in health_out
    assert cli_main(["impact", path, a]) == 0
    impact_out = capsys.readouterr().out
    assert b in impact_out and did in impact_out
    assert cli_main(["query", path, "CLAIMS WHERE score > 0.5"]) == 0
    query_out = capsys.readouterr().out
    assert "alpha" in query_out
    assert cli_main(["query", path, "CLAIMS WHERE bogus = 1"]) == 2
    assert cli_main(["impact", path, "Cmissing"]) == 2
