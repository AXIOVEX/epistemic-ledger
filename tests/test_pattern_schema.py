"""Amendment 3: the pinned claim schema, its validator,
and intake refusal.

The validator enforces the declared types, refuses
loudly, writes nothing, and publishes coverage on every
run — including the fingerprint census (recomputed
fresh; this package stores no fingerprint).
"""

import json
import os

import pytest

from epistemic_ledger import Ledger
from epistemic_ledger.cli import main as cli_main
from epistemic_ledger.pattern import (
    events_from_log,
    proposition_fingerprint,
    validate_ledger,
)


def _store(tmp_path):
    led = Ledger(str(tmp_path / "L"))
    a = led.assert_claim(
        "claim a",
        0.5,
        source="memo section 1",
        falsifier="a drill",
        actor="t",
        t="2026-01-01T00:00:00+00:00",
    )
    led.assert_claim(
        "claim b (legacy-shaped, no pattern fields)",
        0.5,
        actor="t",
        t="2026-01-01T00:01:00+00:00",
    )
    led.close()
    return str(tmp_path / "L"), a


def test_validator_publishes_coverage(tmp_path):
    path, _ = _store(tmp_path)
    report = validate_ledger(events_from_log(path))
    assert report["ok"] is True
    assert report["problems"] == []
    assert report["schema"] == "epistemic-ledger-claims/1"
    cov = report["coverage"]
    assert cov["claims"] == 2
    assert cov["with_source"] == 1
    assert cov["with_falsifier"] == 1
    assert cov["with_does_not_establish"] == 0
    assert cov["distinct_propositions"] == 2
    assert cov["duplicate_propositions"] == 0
    assert cov["duplicate_groups"] == {}


def test_validator_names_type_violations(tmp_path):
    path = str(tmp_path / "raw")
    os.makedirs(path)
    events = [
        {
            "id": "e1",
            "type": "assert",
            "actor": "t",
            "t": "2026-01-01T00:00:00+00:00",
            "payload": {
                "claim_id": "Cx",
                "statement": "a claim",
                "prior": 0.5,
                "falsifier": 42,
            },
        },
        {
            "id": "e2",
            "type": "assert",
            "actor": "t",
            "t": "2026-01-01T00:01:00+00:00",
            "payload": {"claim_id": "Cy", "statement": "", "prior": 1.5},
        },
    ]
    with open(os.path.join(path, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    report = validate_ledger(events_from_log(path))
    assert report["ok"] is False
    text = " ".join(report["problems"])
    assert "falsifier is not a string or null" in text
    assert "statement missing or not a string" in text
    assert "prior missing or not a number in [0, 1]" in text
    # The CLI gate agrees, and exits 1.
    assert cli_main(["pattern-validate", path]) == 1


def test_fingerprint_census_counts_duplicates():
    assert proposition_fingerprint("a  claim\n") == proposition_fingerprint("a claim")
    events = [
        {
            "type": "assert",
            "payload": {
                "claim_id": "C1",
                "statement": "same proposition",
                "prior": 0.5,
            },
        },
        {
            "type": "assert",
            "payload": {
                "claim_id": "C2",
                "statement": "same  proposition ",
                "prior": 0.5,
            },
        },
    ]
    cov = validate_ledger(events)["coverage"]
    assert cov["claims"] == 2
    assert cov["distinct_propositions"] == 1
    assert cov["duplicate_propositions"] == 1
    # The ruling's form: duplicates are grouped by their
    # recomputed fingerprint, not just totaled.
    assert cov["duplicate_groups"] == {proposition_fingerprint("same proposition"): 2}


def test_intake_refusal_writes_nothing(tmp_path):
    led = Ledger(str(tmp_path / "L"))
    before = len(led._events())
    with pytest.raises(ValueError, match="falsifier"):
        led.assert_claim("bad field", 0.5, falsifier=42, actor="t")
    assert len(led._events()) == before
    assert led.list_claims() == []
    led.close()


def test_cli_validate_on_clean_store(tmp_path):
    path, _ = _store(tmp_path)
    assert cli_main(["pattern-validate", path]) == 0
