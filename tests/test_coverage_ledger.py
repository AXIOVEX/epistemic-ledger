"""Coverage tests for ledger.py validation, error, and defensive paths.

Each test asserts real behavior (a refusal, a returned value, a state
change), not merely that a line executed. Gaps targeted are the
missing lines/branches recorded for src/epistemic_ledger/ledger.py.
"""

import builtins
import hashlib
import importlib
import io
import json
import os
import sqlite3
import sys

import pytest

import epistemic_ledger.ledger as ledger_module
from epistemic_ledger.ed25519 import publickey, sign
from epistemic_ledger.ledger import (
    DEFAULT_POLICY,
    DEFAULT_POLICY_RULE,
    Ledger,
    _eval_pred,
    _validate_pred,
    _validate_rule,
)

T1 = "2026-01-01T00:00:00+00:00"
T2 = "2026-01-02T00:00:00+00:00"
T3 = "2026-01-03T00:00:00+00:00"
T4 = "2026-01-04T00:00:00+00:00"
T5 = "2026-01-05T00:00:00+00:00"
T6 = "2026-01-06T00:00:00+00:00"


@pytest.fixture
def ledger(tmp_path):
    L = Ledger(str(tmp_path / "store"))
    yield L
    L.close()


# ----------------------------------------------------------------------
# predicate / rule validation (_validate_pred, _validate_rule, _eval_pred)
# ----------------------------------------------------------------------


def test_validate_pred_rejects_non_dict():
    with pytest.raises(ValueError, match="predicate must be a dict"):
        _validate_pred(["field", "op"])


def test_validate_pred_rejects_non_string_field():
    with pytest.raises(ValueError, match="predicate field must be a string"):
        _validate_pred({"field": 7, "op": "==", "value": 1})


def test_validate_pred_rejects_empty_all_any():
    for bad in ({"all": []}, {"any": "nope"}, {"all": None}):
        with pytest.raises(ValueError, match="non-empty list"):
            _validate_pred(bad)


def test_validate_pred_rejects_malformed_shape():
    with pytest.raises(ValueError, match="malformed predicate"):
        _validate_pred({"field": "x", "op": "=="})


def test_validate_rule_rejects_bad_shapes_actions_effects():
    with pytest.raises(ValueError, match="rule must be"):
        _validate_rule({"action": "declare_contradiction", "effect": "deny"})
    with pytest.raises(ValueError, match="rule must be"):
        _validate_rule("not-a-dict")
    good_when = {"field": "x", "op": "==", "value": 1}
    with pytest.raises(ValueError, match="rule action must be one of"):
        _validate_rule({"action": "explode", "effect": "deny", "when": good_when})
    with pytest.raises(ValueError, match="rule effect must be"):
        _validate_rule(
            {"action": "declare_contradiction", "effect": "shrug", "when": good_when}
        )


def test_validate_rule_rejects_hold_for_non_contradiction_action():
    with pytest.raises(ValueError, match="'hold' requires"):
        _validate_rule(
            {
                "action": "resolve_contradiction",
                "effect": "hold",
                "when": {"field": "x", "op": "==", "value": 1},
            }
        )


def test_eval_pred_missing_field_is_false():
    assert _eval_pred({"field": "nope", "op": "==", "value": 1}, {"x": 1}) is False


def test_eval_pred_comparison_and_membership_ops():
    ctx = {"n": 5, "tag": "red"}
    assert _eval_pred({"field": "n", "op": "<", "value": 6}, ctx) is True
    assert _eval_pred({"field": "n", "op": "<", "value": 5}, ctx) is False
    assert _eval_pred({"field": "n", "op": "<=", "value": 5}, ctx) is True
    assert _eval_pred({"field": "n", "op": ">", "value": 4}, ctx) is True
    assert _eval_pred({"field": "n", "op": ">", "value": 5}, ctx) is False
    assert _eval_pred({"field": "tag", "op": "in", "value": ["red", "blue"]}, ctx)
    assert not _eval_pred({"field": "tag", "op": "in", "value": ["blue"]}, ctx)
    assert _eval_pred({"field": "tag", "op": "not_in", "value": ["blue"]}, ctx)
    assert not _eval_pred({"field": "tag", "op": "not_in", "value": ["red"]}, ctx)


def test_eval_pred_type_error_and_unknown_op_are_false():
    # int < str raises TypeError inside the comparison: fail-closed False.
    assert _eval_pred({"field": "n", "op": "<", "value": "s"}, {"n": 1}) is False
    # An op outside the known set falls through to False.
    assert _eval_pred({"field": "n", "op": "~~", "value": 1}, {"n": 1}) is False


def test_register_policy_validates_rule_through_public_api(ledger):
    with pytest.raises(ValueError, match="malformed predicate"):
        ledger.register_policy(
            "bad-rule-policy",
            "desc",
            version=1,
            rule={
                "action": "declare_contradiction",
                "effect": "deny",
                "when": {"bogus": 1},
            },
        )
    assert ledger.audit_policy("bad-rule-policy") is None


# ----------------------------------------------------------------------
# context manager, missing log file, verify_store findings
# ----------------------------------------------------------------------


def test_ledger_context_manager(tmp_path):
    path = str(tmp_path / "ctx")
    with Ledger(path) as L:
        cid = L.assert_claim("inside", 0.5, t=T1)
        assert L.get_claim(cid)["statement"] == "inside"
    # __exit__ closed the store: the lock is released, reopening works.
    with Ledger(path) as L2:
        assert L2.get_claim(cid) is not None


def test_events_and_queries_with_missing_log_file(tmp_path):
    L = Ledger(str(tmp_path / "s"), recover=False)
    cid = L.assert_claim("will lose its log", 0.5, t=T1)
    os.remove(L.log_path)
    assert L._events() == []
    assert L.changed(T1, T6) == []
    # Cached read views keyed by log size take the OSError (size -1) arm.
    assert [c["claim_id"] for c in L.list_claims()] == [cid]
    assert L.decisions() == []
    impact = L.impact(cid)
    assert impact["claim_id"] == cid and impact["nodes"] == []
    L.close()


def test_verify_store_blank_line_missing_field_and_duplicate_id(ledger):
    cid = ledger.assert_claim("ground truth", 0.5, t=T1)
    assert ledger.verify_store()["ok"]
    with open(ledger.log_path, "a", encoding="utf-8") as f:
        f.write("\n")  # blank line: skipped, not a finding
    assert ledger.verify_store()["ok"]
    with open(ledger.log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event_id": "EBAD", "t": T2, "type": "decision"}) + "\n")
    problems = ledger.verify_store()["problems"]
    assert any("missing payload" in p for p in problems)
    # Duplicate an existing assert line verbatim: duplicate event_id.
    with open(ledger.log_path, encoding="utf-8") as f:
        lines = f.readlines()
    assert_line = next(line for line in lines if '"assert"' in line)
    with open(ledger.log_path, "a", encoding="utf-8") as f:
        f.write(assert_line)
    problems = ledger.verify_store()["problems"]
    assert any("duplicate event_id" in p for p in problems)
    assert ledger.get_claim(cid) is not None


def test_verify_store_terminal_claim_with_live_row_is_a_finding(ledger):
    old = ledger.assert_claim("to be replaced", 0.5, t=T1)
    ledger.supersede(old, "replacement", 0.6, reason="wrong", source="test", t=T2)
    assert ledger.verify_store()["ok"]
    # Plant a live row for the terminal (superseded) claim.
    ledger.db.execute(
        """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                              valid_to, score, score_kind, status,
                              materiality, critical, entrenchment, writer)
           VALUES (?, ?, 'planted', NULL, NULL, 0.5, 'credence',
                   'active', 0.05, 0, 0.5, NULL)""",
        (old, T3),
    )
    ledger.db.commit()
    problems = ledger.verify_store()["problems"]
    assert any(
        "terminal lifecycle status but still has a live row" in p for p in problems
    )


def test_verify_store_referenced_ghost_claims(ledger):
    real = ledger.assert_claim("real", 0.5, t=T1)
    # A ghost referenced only by support_edges (not by claims) is
    # reported against the referencing table.
    ledger.db.execute(
        """INSERT INTO support_edges(claim_id, supports_id, kind, p_given,
                                     p_given_not, strength, txn_from)
           VALUES ('GHOSTEDGE', ?, 'evidential', 0.9, 0.1, 1.0, ?)""",
        (real, T1),
    )
    # A ghost present in claims AND referenced by an edge is reported
    # once (against claims); the referenced-loop skips it.
    ledger.db.execute(
        """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                              valid_to, score, score_kind, status,
                              materiality, critical, entrenchment, writer)
           VALUES ('GHOSTBOTH', ?, 'planted', NULL, NULL, 0.5, 'credence',
                   'active', 0.05, 0, 0.5, NULL)""",
        (T1,),
    )
    ledger.db.execute(
        """INSERT INTO support_edges(claim_id, supports_id, kind, p_given,
                                     p_given_not, strength, txn_from)
           VALUES ('GHOSTBOTH', ?, 'evidential', 0.9, 0.1, 1.0, ?)""",
        (real, T1),
    )
    ledger.db.commit()
    problems = ledger.verify_store()["problems"]
    assert any("GHOSTEDGE" in p and "support_edges" in p for p in problems)
    assert sum("GHOSTBOTH" in p for p in problems) == 1
    assert any("GHOSTBOTH" in p and "claims" in p for p in problems)


# ----------------------------------------------------------------------
# unknown-claim refusals across the public surface
# ----------------------------------------------------------------------


def test_unknown_claim_refusals(ledger):
    with pytest.raises(KeyError):
        ledger.manual_score("C-unknown", 0.5, t=T1)
    with pytest.raises(KeyError):
        ledger.set_entrenchment("C-unknown", 0.5, t=T1)
    with pytest.raises(KeyError):
        ledger.supersede("C-unknown", "x", 0.5, reason="r", source="s", t=T1)
    with pytest.raises(KeyError):
        ledger.get_entrenchment("C-unknown")
    with pytest.raises(KeyError):
        ledger.effective_entrenchment("C-unknown")
    with pytest.raises(KeyError):
        ledger.assign_topic("C-unknown", "topic", t=T1)
    with pytest.raises(KeyError):
        ledger.set_combo("C-unknown", "noisy-and", t=T1)
    with pytest.raises(KeyError):
        ledger.declare_contradiction("C-unknown", "C-also-unknown", t=T1)


def test_add_support_validation(ledger):
    a = ledger.assert_claim("a", 0.5, t=T1)
    b = ledger.assert_claim("b", 0.5, t=T1)
    with pytest.raises(ValueError, match="kind must be one of"):
        ledger.add_support(a, b, "vibes", t=T2)
    with pytest.raises(ValueError, match="strength must be in"):
        ledger.add_support(a, b, "evidential", strength=1.5, t=T2)
    with pytest.raises(ValueError, match="strength must be in"):
        ledger.add_support(a, b, "evidential", strength=-0.1, t=T2)
    with pytest.raises(KeyError, match="both claims must exist"):
        ledger.add_support(a, "C-unknown", "evidential", t=T2)
    with pytest.raises(KeyError, match="both claims must exist"):
        ledger.add_support("C-unknown", b, "evidential", t=T2)
    # The refusals wrote no edge.
    assert ledger.why(a) == []


def test_set_combo_validation(ledger):
    a = ledger.assert_claim("a", 0.5, t=T1)
    with pytest.raises(ValueError, match="leak must be in"):
        ledger.set_combo(a, "noisy-and", leak=1.5, t=T2)
    with pytest.raises(ValueError, match="strengths must be in"):
        ledger.set_combo(a, "noisy-or", strengths={a: 2.0}, t=T2)
    assert ledger.get_combo(a) is None


def test_combine_score_empty_parents_is_none():
    assert Ledger._combine_score("noisy-and", 0.0, {}) is None
    assert Ledger._combine_score("noisy-or", 0.0, {}) is None


def test_retract_support_without_edge_raises(ledger):
    a = ledger.assert_claim("a", 0.5, t=T1)
    b = ledger.assert_claim("b", 0.5, t=T1)
    with pytest.raises(KeyError, match="no live support edge"):
        ledger.retract_support(a, b, t=T2)


# ----------------------------------------------------------------------
# writers, keys, and verdict signatures
# ----------------------------------------------------------------------


def test_register_writer_rejects_short_public_key(ledger):
    with pytest.raises(ValueError, match="public_key must be 32 bytes"):
        ledger.register_writer("w", "owner", public_key="abcd", t=T1)
    assert ledger.get_writer("w") is None


def test_writer_pubkey_none_writer_is_none(ledger):
    assert ledger.get_writer_pubkey(None) is None
    assert ledger.audit_writer_pubkey(None, T1) is None
    assert ledger.get_writer_pubkey("never-registered") is None


def test_require_verdict_signature_rejects_nonhex_signature(ledger):
    seed = bytes(range(32))
    ledger.register_writer("signer", "owner", public_key=publickey(seed).hex(), t=T1)
    msg = Ledger.verdict_message("resolve", "X1", "signer")
    with pytest.raises(PermissionError, match="invalid verdict signature"):
        ledger._require_verdict_signature("signer", "not-hex!", msg)
    # A well-formed signature over the message is accepted and recorded.
    good = sign(seed, msg.encode()).hex()
    out = ledger._require_verdict_signature("signer", good, msg)
    assert out == {"signer": "signer", "signature": good, "signed_message": msg}


def test_verify_verdict_signatures_flags_nonhex_signature(ledger):
    seed = bytes(range(32))
    ledger.register_writer("signer", "owner", public_key=publickey(seed).hex(), t=T1)
    ev = ledger._emit(
        "contradiction_dismissed",
        {
            "held_id": "H1",
            "signer": "signer",
            "signature": "zz-not-hex",
            "signed_message": "anything",
        },
        actor="system",
        t=T2,
    )
    result = ledger.verify_verdict_signatures()
    assert result["checked"] == 1
    assert result["valid"] == 0
    assert result["invalid"] == [ev["event_id"]]


def test_verify_deep_reports_signature_audit(ledger):
    seed = bytes(range(32))
    ledger.register_writer("signer", "owner", public_key=publickey(seed).hex(), t=T1)
    msg = "axiovex-ledger/verdict/v1|action=resolve|id=X1|writer=signer"
    ledger._emit(
        "contradiction_resolved",
        {
            "contradiction_id": "X1",
            "signer": "signer",
            "signature": sign(seed, msg.encode()).hex(),
            "signed_message": msg,
        },
        actor="system",
        t=T2,
    )
    deep = ledger.verify(deep=True)
    assert deep["ok"] is True
    assert deep["verdict_signatures"] == {"checked": 1, "valid": 1, "invalid": []}
    shallow = ledger.verify()
    assert "verdict_signatures" not in shallow

    bad = ledger._emit(
        "contradiction_resolved",
        {
            "contradiction_id": "X2",
            "signer": "signer",
            "signature": sign(seed, b"a different message").hex(),
            "signed_message": msg,
        },
        actor="system",
        t=T3,
    )
    deep2 = ledger.verify(deep=True)
    assert deep2["ok"] is False
    assert deep2["verdict_signatures"]["invalid"] == [bad["event_id"]]


def test_escalate_contradiction_rejects_bad_decision(ledger):
    ledger.register_writer("boss", "owner", t=T1)
    with pytest.raises(ValueError, match="decision must be"):
        ledger.escalate_contradiction("H-none", "ponder", writer="boss", t=T2)


# ----------------------------------------------------------------------
# policy gate: deny path and the rule-less default-policy fallback
# ----------------------------------------------------------------------


def test_declare_contradiction_denied_by_custom_policy(ledger):
    ledger.register_policy(
        "deny-declarations",
        "no declarations at all",
        version=1,
        rule={
            "action": "declare_contradiction",
            "effect": "deny",
            "when": {"field": "target_entrenchment", "op": ">=", "value": 0.0},
        },
        t=T1,
    )
    a = ledger.assert_claim("a", 0.5, t=T1)
    b = ledger.assert_claim("b", 0.5, t=T1)
    with pytest.raises(PermissionError, match="denies declare_contradiction"):
        ledger.declare_contradiction(a, b, t=T2)
    denied = [e for e in ledger._events() if e["type"] == "policy_denied"]
    assert len(denied) == 1 and denied[0]["payload"]["policy"] == "deny-declarations"


def test_policy_gate_fallback_when_default_policy_row_has_no_rule(ledger):
    # Simulate a legacy store: the default policy's live row predates
    # rules, so the compiled-in fallback predicate must still hold
    # non-owner declarations against axiomatic claims.
    ledger.db.execute(
        "UPDATE policies SET rule = NULL WHERE name = ?", (DEFAULT_POLICY[0],)
    )
    ledger.db.commit()
    ledger.register_writer("contrib", "contributor", t=T1)
    axiom = ledger.assert_claim("axiom", 0.9, entrenchment=1.0, t=T1)
    other = ledger.assert_claim("other", 0.1, t=T1)
    held_id = ledger.declare_contradiction(axiom, other, writer="contrib", t=T2)
    held = ledger.held_contradictions()
    assert [e["event_id"] for e in held] == [held_id]
    assert held[0]["payload"]["policy"] == DEFAULT_POLICY[0]
    assert ledger.open_contradictions() == []
    # The fallback predicate also evaluates false: a declaration whose
    # target is below the axiomatic threshold is not held.
    low_a = ledger.assert_claim("low a", 0.5, entrenchment=0.5, t=T1)
    low_b = ledger.assert_claim("low b", 0.5, entrenchment=0.5, t=T1)
    free_id = ledger.declare_contradiction(low_a, low_b, writer="contrib", t=T2)
    assert [e["event_id"] for e in ledger.open_contradictions()] == [free_id]


# ----------------------------------------------------------------------
# learn_entrenchment branches
# ----------------------------------------------------------------------


def _outcomes(L, cid, outcomes, start=T2):
    for i, outcome in enumerate(outcomes):
        L.record_outcome(cid, outcome, t=f"2026-01-0{2 + i}T00:00:00+00:00")
    assert start  # times are the explicit ones above


def test_learn_entrenchment_skips_dead_claim_with_outcomes(ledger):
    cid = ledger.assert_claim("doomed", 0.8, t=T1)
    _outcomes(ledger, cid, [True, True, False])
    ledger.set_claim_status(
        cid, "dead", reason="no longer applies", source="test", t=T5
    )
    report = ledger.learn_entrenchment(min_outcomes=3, t=T6)
    assert all(r["claim_id"] != cid for r in report)


def test_learn_entrenchment_no_change_when_brier_matches_current(ledger):
    # score 0.8, outcomes [1,1,0]: Brier = (0.04+0.04+0.64)/3 = 0.24,
    # so 1 - Brier = 0.76, exactly the claim's current entrenchment.
    cid = ledger.assert_claim("calibrated", 0.8, entrenchment=0.76, t=T1)
    _outcomes(ledger, cid, [True, True, False])
    report = ledger.learn_entrenchment(min_outcomes=3, t=T5)
    assert report == []
    assert ledger.get_entrenchment(cid) == pytest.approx(0.76)


def test_learn_entrenchment_stability_skips_dead_flip_flopper(ledger):
    cid = ledger.assert_claim("flip", 0.4, t=T1)
    for i, score in enumerate([0.6, 0.4, 0.6, 0.4]):
        ledger.manual_score(cid, score, t=f"2026-01-0{2 + i}T00:00:00+00:00")
    ledger.supersede(cid, "flip v2", 0.5, reason="replaced", source="test", t=T6)
    report = ledger.learn_entrenchment(t="2026-01-07T00:00:00+00:00")
    assert all(r["claim_id"] != cid for r in report)


def test_learn_entrenchment_stability_noop_at_zero_entrenchment(ledger):
    cid = ledger.assert_claim("weightless", 0.4, entrenchment=0.0, t=T1)
    for i, score in enumerate([0.6, 0.4, 0.6, 0.4]):
        ledger.manual_score(cid, score, t=f"2026-01-0{2 + i}T00:00:00+00:00")
    report = ledger.learn_entrenchment(t=T6)
    assert report == []
    assert ledger.get_entrenchment(cid) == 0.0


def test_learn_entrenchment_ignores_outcome_predating_claim(ledger):
    cid = ledger.assert_claim("later", 0.9, t=T3)
    # Outcome timestamped before the claim existed: no version was
    # live then, so it contributes no history.
    ledger.record_outcome(cid, True, t=T1)
    report = ledger.learn_entrenchment(min_outcomes=1, t=T4)
    assert report == []


# ----------------------------------------------------------------------
# revisit loop branches
# ----------------------------------------------------------------------


def test_revisit_skips_dependent_with_no_live_row(ledger):
    root = ledger.assert_claim("root", 0.5, t=T1)
    dep = ledger.assert_claim("dep", 0.5, t=T1)
    ledger.add_support(dep, root, "evidential", p_given=0.9, p_given_not=0.1, t=T1)
    ledger.set_claim_status(dep, "dead", reason="retired", source="test", t=T2)
    report = ledger._revisit(root, {root: 0.95}, t=T3)
    assert report["closure_size"] == 1
    assert report["updates"] == []


def test_revisit_combo_cutoff_when_no_parent_updated(ledger):
    root = ledger.assert_claim("root", 0.5, t=T1)
    mid = ledger.assert_claim("mid", 0.5, t=T1)
    # p_given == p_given_not: Jeffrey leaves mid at 0.5 whatever root
    # does, so mid is cutoff-skipped and never enters `updated`.
    ledger.add_support(mid, root, "evidential", p_given=0.5, p_given_not=0.5, t=T1)
    combo = ledger.assert_claim("combo", 0.5, t=T1)
    ledger.add_support(combo, mid, "evidential", p_given=0.9, p_given_not=0.1, t=T1)
    ledger.set_combo(combo, "noisy-and", t=T1)
    report = ledger._revisit(root, {root: 0.95}, t=T2)
    assert report["updates"] == []
    assert report["cutoff_skipped"] == 2  # mid (delta 0) and combo (no parent updated)
    assert ledger.get_score(combo) == pytest.approx(0.5)


def test_revisit_combo_ignores_parent_with_no_live_row(ledger):
    root = ledger.assert_claim("root", 0.5, t=T1)
    parent = ledger.assert_claim("parent", 0.5, t=T1)
    ledger.add_support(parent, root, "evidential", p_given=1.0, p_given_not=0.0, t=T1)
    dead = ledger.assert_claim("dead parent", 0.9, t=T1)
    combo = ledger.assert_claim("combo", 0.0, t=T1)
    ledger.add_support(combo, parent, "evidential", t=T1)
    ledger.add_support(combo, dead, "evidential", t=T1)
    ledger.set_combo(combo, "noisy-or", leak=0.0, t=T1)
    ledger.set_claim_status(dead, "dead", reason="retired", source="test", t=T2)
    report = ledger._revisit(root, {root: 1.0}, t=T3)
    updated = {u["claim_id"]: u["new"] for u in report["updates"]}
    assert updated[parent] == pytest.approx(1.0)
    # noisy-or over the single live parent at 1.0 saturates to 1.0;
    # the dead parent contributes nothing.
    assert updated[combo] == pytest.approx(1.0)


# ----------------------------------------------------------------------
# contradictions: detection after resolution, resolution of dead claims
# ----------------------------------------------------------------------


def _interval_pair(L):
    x = L.assert_claim("x", 0.95, entrenchment=0.9, t=T1)
    y = L.assert_claim("y", 0.05, entrenchment=0.1, t=T1)
    L.set_interval(x, 0.9, 1.0, t=T1)
    L.set_interval(y, 0.0, 0.1, t=T1)
    return x, y


def test_detect_contradictions_does_not_redeclare_resolved_pair(ledger):
    x, y = _interval_pair(ledger)
    cid = ledger.declare_contradiction(x, y, t=T2)
    outcome = ledger.resolve_contradiction(cid, t=T3)
    assert outcome["resolved"] is True
    # The resolved pair is in the detector's seen set (via the
    # contradiction_resolved event), so detection stays quiet.
    assert ledger.detect_contradictions(t=T4) == []
    assert ledger.open_contradictions() == []


def test_resolve_contradiction_with_dead_claim_reports_not_live(ledger):
    a = ledger.assert_claim("a", 0.9, entrenchment=0.9, t=T1)
    b = ledger.assert_claim("b", 0.1, entrenchment=0.1, t=T1)
    cid = ledger.declare_contradiction(a, b, t=T2)
    ledger.set_claim_status(b, "dead", reason="gone", source="test", t=T3)
    outcome = ledger.resolve_contradiction(cid, t=T4)
    assert outcome == {
        "resolved": False,
        "reason": "claim not live",
        "contradiction_id": cid,
    }
    unresolved = [
        e for e in ledger._events() if e["type"] == "contradiction_unresolved"
    ]
    assert len(unresolved) == 1
    assert unresolved[0]["payload"]["reason"] == "claim no longer live"


# ----------------------------------------------------------------------
# intervals: total-conflict refusal inside combine_interval
# ----------------------------------------------------------------------


def test_combine_interval_total_conflict_is_refused(ledger):
    cid = ledger.assert_claim("certain", 1.0, t=T1)
    ledger.set_interval(cid, 1.0, 1.0, t=T1)
    # New evidence is certain-False against a certain-True interval:
    # Dempster's rule has total conflict and raises; the ledger
    # converts that into a recorded refusal with K = 1.0.
    result = ledger.combine_interval(cid, 0.0, 1.0, 0.0, t=T2)
    assert result == {"combined": False, "conflict": 1.0}
    assert ledger.get_interval(cid) == (1.0, 1.0)
    refused = [e for e in ledger._events() if e["type"] == "interval_refused"]
    assert len(refused) == 1 and refused[0]["payload"]["conflict"] == 1.0


def test_combine_interval_requires_interval_and_unit_mass(ledger):
    cid = ledger.assert_claim("plain", 0.5, t=T1)
    with pytest.raises(KeyError, match="no interval set"):
        ledger.combine_interval(cid, 0.5, 0.25, 0.25, t=T1)
    ledger.set_interval(cid, 0.2, 0.8, t=T1)
    with pytest.raises(ValueError, match="masses must sum to 1"):
        ledger.combine_interval(cid, 0.5, 0.5, 0.5, t=T2)


# ----------------------------------------------------------------------
# schema backfill (_ensure_columns) on a legacy-shaped database
# ----------------------------------------------------------------------


def test_ensure_columns_backfills_legacy_database(tmp_path):
    path = tmp_path / "legacy"
    path.mkdir()
    db = sqlite3.connect(str(path / "ledger.db"))
    db.executescript(
        """
        CREATE TABLE claims(
          claim_id TEXT NOT NULL, txn_from TEXT NOT NULL, txn_to TEXT,
          statement TEXT NOT NULL, valid_from TEXT, valid_to TEXT,
          score REAL NOT NULL, score_kind TEXT NOT NULL DEFAULT 'credence',
          status TEXT NOT NULL DEFAULT 'active',
          materiality REAL NOT NULL DEFAULT 0.05,
          critical INTEGER NOT NULL DEFAULT 0,
          entrenchment REAL NOT NULL DEFAULT 0.5,
          PRIMARY KEY (claim_id, txn_from));
        CREATE TABLE support_edges(
          claim_id TEXT NOT NULL, supports_id TEXT NOT NULL,
          kind TEXT NOT NULL, p_given REAL NOT NULL,
          p_given_not REAL NOT NULL, txn_from TEXT NOT NULL, txn_to TEXT,
          PRIMARY KEY (claim_id, supports_id, txn_from));
        CREATE TABLE writers(
          writer_id TEXT NOT NULL, txn_from TEXT NOT NULL, txn_to TEXT,
          tier TEXT NOT NULL, PRIMARY KEY (writer_id, txn_from));
        CREATE TABLE policies(
          name TEXT NOT NULL, txn_from TEXT NOT NULL, txn_to TEXT,
          description TEXT NOT NULL, version INTEGER NOT NULL,
          PRIMARY KEY (name, txn_from));
        """
    )
    db.commit()
    db.close()
    L = Ledger(str(path), recover=False)
    try:
        cols = {
            t: [r[1] for r in L.db.execute(f"PRAGMA table_info({t})")]
            for t in ("claims", "support_edges", "writers", "policies")
        }
        assert "strength" in cols["support_edges"]
        assert "writer" in cols["claims"]
        assert {"source", "falsifier", "does_not_establish"} <= set(cols["claims"])
        assert "pubkey" in cols["writers"]
        assert "rule" in cols["policies"]
        cid = L.assert_claim("on a backfilled store", 0.5, t=T1)
        assert L.get_claim(cid)["statement"] == "on a backfilled store"
    finally:
        L.close()


# ----------------------------------------------------------------------
# projection rebuild: fold branches and failure handling
# ----------------------------------------------------------------------


def _write_log(path, events):
    with open(os.path.join(path, "events.jsonl"), "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _event(event_id, etype, payload, t=T1):
    return {
        "event_id": event_id,
        "t": t,
        "actor": "test",
        "type": etype,
        "payload": payload,
    }


def _assert_payload(claim_id, statement, prior, **extra):
    payload = {
        "claim_id": claim_id,
        "statement": statement,
        "prior": prior,
        "writer": None,
        "valid_from": None,
        "valid_to": None,
        "score_kind": "credence",
        "materiality": 0.05,
        "critical": False,
    }
    payload.update(extra)
    return payload


def test_rebuild_fold_derives_entrenchment_from_writer_tier(tmp_path):
    path = str(tmp_path / "fold")
    os.makedirs(path)
    _write_log(
        path,
        [
            _event(
                "E1",
                "writer_registered",
                {"writer_id": "w1", "tier": "owner", "pubkey": None},
            ),
            # No explicit entrenchment in either assert: the fold must
            # derive it from the writer's tier (owner -> 0.75), and an
            # unregistered writer falls back to 0.25.
            _event("E2", "assert", _assert_payload("CA", "by owner", 0.5, writer="w1")),
            _event(
                "E3", "assert", _assert_payload("CB", "by ghost", 0.5, writer="ghost")
            ),
        ],
    )
    result = Ledger.rebuild_projection(path)
    assert result == {"events": 3, "claims_checked": 2, "ok": True}
    L = Ledger(path, recover=False)
    try:
        assert L.get_entrenchment("CA") == pytest.approx(0.75)
        assert L.get_entrenchment("CB") == pytest.approx(0.25)
    finally:
        L.close()


def test_rebuild_fold_fills_default_policy_fields(tmp_path):
    path = str(tmp_path / "foldpolicy")
    os.makedirs(path)
    _write_log(
        path,
        [
            _event(
                "E1",
                "policy_registered",
                {
                    "name": DEFAULT_POLICY[0],
                    "version": 2,
                    "description": None,
                    "rule": None,
                },
            )
        ],
    )
    assert Ledger.rebuild_projection(path)["ok"] is True
    L = Ledger(path, recover=False)
    try:
        live = L.audit_policy(DEFAULT_POLICY[0])
        assert live["description"] == DEFAULT_POLICY[1]
        assert live["rule"] == DEFAULT_POLICY_RULE
    finally:
        L.close()


def test_rebuild_fold_refuses_event_for_unknown_claim(tmp_path):
    path = str(tmp_path / "foldbad")
    os.makedirs(path)
    _write_log(
        path,
        [
            _event(
                "E1",
                "score_revision",
                {"claim_id": "C-ghost", "old_score": 0.1, "new_score": 0.2},
            )
        ],
    )
    with pytest.raises(ValueError, match="rebuild: event for unknown claim"):
        Ledger.rebuild_projection(path)


def test_rebuild_replaces_stale_scratch_file(tmp_path):
    path = str(tmp_path / "foldscratch")
    L = Ledger(path)
    L.assert_claim("kept", 0.5, t=T1)
    L.close()
    scratch = os.path.join(path, "ledger.db.rebuild-tmp")
    with open(scratch, "wb") as f:
        f.write(b"stale scratch from a crashed rebuild")
    result = Ledger.rebuild_projection(path)
    assert result["ok"] is True
    assert not os.path.exists(scratch)


def test_rebuild_failure_restores_previous_projection(tmp_path):
    path = str(tmp_path / "foldrestore")
    L = Ledger(path)
    kept = L.assert_claim("original", 0.5, t=T1)
    L.close()
    db_path = os.path.join(path, "ledger.db")
    with open(db_path, "rb") as f:
        before = hashlib.sha256(f.read()).hexdigest()
    # Two asserts sharing one event_id: the fold succeeds, but
    # verification fails on the duplicate, so the original projection
    # must be restored byte for byte.
    _write_log(
        path,
        [
            _event("EDUP", "assert", _assert_payload("CG1", "one", 0.5)),
            _event("EDUP", "assert", _assert_payload("CG2", "two", 0.5)),
        ],
    )
    with pytest.raises(RuntimeError, match="rebuilt projection failed verification"):
        Ledger.rebuild_projection(path)
    with open(db_path, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == before
    L2 = Ledger(path, recover=False)
    try:
        assert L2.get_claim(kept) is not None
    finally:
        L2.close()


# ----------------------------------------------------------------------
# crash recovery at open
# ----------------------------------------------------------------------


def test_open_refuses_unrecoverable_store(tmp_path):
    path = str(tmp_path / "broken")
    L = Ledger(path)
    L.assert_claim("one", 0.5, t=T1)
    L.assert_claim("two", 0.5, t=T2)
    L.close()
    log_path = os.path.join(path, "events.jsonl")
    with open(log_path, encoding="utf-8") as f:
        lines = f.readlines()
    lines[1] = "this is not json\n"  # interior corruption, not a torn tail
    with open(log_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    with pytest.raises(RuntimeError, match="cannot be recovered at open"):
        Ledger(path)


def test_open_fails_when_rebuild_leaves_store_unverified(tmp_path, monkeypatch):
    path = str(tmp_path / "unfixable")
    L = Ledger(path)
    L.assert_claim("one", 0.5, t=T1)
    L.close()
    log_path = os.path.join(path, "events.jsonl")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("not json at all\n")
    # A rebuild that returns without repairing anything (the seam a
    # no-op projection rebuild would be) leaves verification failing:
    # open must refuse rather than serve the damaged store.
    monkeypatch.setattr(
        Ledger,
        "rebuild_projection",
        classmethod(lambda cls, p: {"events": 0, "claims_checked": 0, "ok": True}),
    )
    with pytest.raises(RuntimeError, match="does not verify after crash recovery"):
        Ledger(path)


def test_rebuild_failure_without_previous_projection(tmp_path):
    path = str(tmp_path / "foldnobackup")
    os.makedirs(path)
    _write_log(
        path,
        [
            _event("EDUP", "assert", _assert_payload("CG1", "one", 0.5)),
            _event("EDUP", "assert", _assert_payload("CG2", "two", 0.5)),
        ],
    )
    # No ledger.db exists, so there is no backup to restore; the
    # verification failure still raises.
    with pytest.raises(RuntimeError, match="rebuilt projection failed verification"):
        Ledger.rebuild_projection(path)
    assert not os.path.exists(os.path.join(path, "ledger.db.bak"))


def test_open_torn_tail_readback_failure_raises(tmp_path, monkeypatch):
    path = str(tmp_path / "torn")
    L = Ledger(path)
    L.assert_claim("committed", 0.5, t=T1)
    L.close()
    log_path = os.path.join(path, "events.jsonl")
    with open(log_path, "ab") as f:
        f.write(b'{"event_id": "EPARTIAL"')  # torn tail, no newline

    real_open = builtins.open
    rb_reads = {"n": 0}

    def flaky_open(file, mode="r", *args, **kwargs):
        if os.fspath(file) == log_path and mode == "rb":
            rb_reads["n"] += 1
            if rb_reads["n"] >= 2:
                # The read-back after truncation returns more bytes
                # than the truncation target: verification must fail.
                with real_open(file, "rb") as fh:
                    return io.BytesIO(fh.read() + b"extra")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)
    with pytest.raises(RuntimeError, match="torn-tail truncation failed"):
        Ledger(path)
    monkeypatch.undo()
    # The truncation itself landed before the failed read-back, so a
    # clean open now succeeds with the committed claim intact.
    L2 = Ledger(path)
    try:
        assert L2.open_report["torn_bytes"] == 0
        assert len(L2.list_claims()) == 1
    finally:
        L2.close()


# ----------------------------------------------------------------------
# simulated revision (impact, propagated mode) branches
# ----------------------------------------------------------------------


def test_impact_propagated_skips_dead_dependent(ledger):
    root = ledger.assert_claim("root", 0.8, t=T1)
    dep = ledger.assert_claim("dep", 0.5, t=T1)
    ledger.add_support(dep, root, "evidential", p_given=0.9, p_given_not=0.1, t=T1)
    ledger.set_claim_status(dep, "dead", reason="gone", source="test", t=T2)
    result = ledger.impact(root, mode="propagated", revised_score=0.0)
    # The root's own revision is reported; the dead dependent is
    # skipped by the simulation (no live version to move).
    assert [m["claim_id"] for m in result["movements"]] == [root]
    assert result["revised_score"] == 0.0


def test_impact_propagated_combo_cutoff_when_parent_unmoved(ledger):
    root = ledger.assert_claim("root", 0.5, t=T1)
    mid = ledger.assert_claim("mid", 0.5, t=T1)
    ledger.add_support(mid, root, "evidential", p_given=0.5, p_given_not=0.5, t=T1)
    combo = ledger.assert_claim("combo", 0.5, t=T1)
    ledger.add_support(combo, mid, "evidential", p_given=0.9, p_given_not=0.1, t=T1)
    ledger.set_combo(combo, "noisy-and", t=T1)
    result = ledger.impact(root, mode="propagated", revised_score=1.0)
    # mid's simulated score cannot move (equal likelihoods), so the
    # combo dependent is never recomputed; only the root itself moves.
    assert [m["claim_id"] for m in result["movements"]] == [root]


def test_impact_propagated_combo_ignores_dead_parent(ledger):
    root = ledger.assert_claim("root", 0.5, t=T1)
    parent = ledger.assert_claim("parent", 0.5, t=T1)
    ledger.add_support(parent, root, "evidential", p_given=1.0, p_given_not=0.0, t=T1)
    dead = ledger.assert_claim("dead parent", 0.9, t=T1)
    combo = ledger.assert_claim("combo", 0.0, t=T1)
    ledger.add_support(combo, parent, "evidential", t=T1)
    ledger.add_support(combo, dead, "evidential", t=T1)
    ledger.set_combo(combo, "noisy-or", leak=0.0, t=T1)
    ledger.set_claim_status(dead, "dead", reason="gone", source="test", t=T2)
    result = ledger.impact(root, mode="propagated", revised_score=1.0)
    moved = {m["claim_id"]: m["new"] for m in result["movements"]}
    assert moved[parent] == pytest.approx(1.0)
    assert moved[combo] == pytest.approx(1.0)


# ----------------------------------------------------------------------
# impact caps: decisions over max_depth, path listing caps, saturation
# ----------------------------------------------------------------------


def test_impact_max_depth_drops_decision_beyond_depth(ledger):
    root = ledger.assert_claim("root", 0.5, t=T1)
    child = ledger.assert_claim("child", 0.5, t=T1)
    ledger.add_support(child, root, "evidential", t=T1)
    decision_id = ledger.record_decision("d", [child], t=T2)
    result = ledger.impact(root, max_depth=1)
    # The child (distance 1) survives; the decision sits at distance 2
    # and is dropped by the depth cap, which is reported.
    assert [n["id"] for n in result["nodes"]] == [child]
    assert result["truncated"] is True
    assert result["truncation_reasons"] == ["max_depth"]
    assert decision_id not in [n["id"] for n in result["nodes"]]
    full = ledger.impact(root)
    assert decision_id in [n["id"] for n in full["nodes"]]


def test_impact_path_listing_caps(ledger):
    root = ledger.assert_claim("root", 0.5, t=T1)
    a = ledger.assert_claim("a", 0.5, t=T1)
    b = ledger.assert_claim("b", 0.5, t=T1)
    c = ledger.assert_claim("c", 0.5, t=T1)
    ledger.add_support(a, root, "evidential", t=T1)
    ledger.add_support(b, root, "evidential", t=T1)
    ledger.add_support(c, a, "evidential", t=T1)
    ledger.add_support(c, b, "evidential", t=T1)

    ledger._MAX_PATHS_PER_NODE = 1
    capped = ledger.impact(root)
    node_c = next(n for n in capped["nodes"] if n["id"] == c)
    assert node_c["path_count"] == 2  # both shortest paths counted
    assert len(node_c["paths"]) == 1  # but only one listed
    assert capped["truncated"] is True
    assert "paths" in capped["truncation_reasons"]
    del ledger._MAX_PATHS_PER_NODE

    ledger._MAX_PATH_ELEMENTS = 1
    starved = ledger.impact(root)
    assert starved["truncated"] is True
    assert all(n["paths"] == [] for n in starved["nodes"])
    del ledger._MAX_PATH_ELEMENTS


def test_impact_path_count_saturates(ledger):
    root = ledger.assert_claim("layer0", 0.5, t=T1)
    prev = [root]
    layers = 52
    for i in range(layers):
        cur = [ledger.assert_claim(f"layer{i + 1}-{j}", 0.5, t=T1) for j in range(2)]
        for node in cur:
            for supporter in prev:
                ledger.add_support(node, supporter, "evidential", t=T1)
        prev = cur
    result = ledger.impact(root)
    deepest = max(result["nodes"], key=lambda n: n["distance"])
    assert deepest["distance"] == layers
    # 2**52 shortest paths saturate the counter at 10**15.
    assert deepest["path_count"] == 10**15


# ----------------------------------------------------------------------
# fcntl import fallback (non-Unix arm of the module import)
# ----------------------------------------------------------------------


def test_fcntl_import_fallback_sets_none():
    real_import = builtins.__import__

    def no_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("fcntl unavailable")
        return real_import(name, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(builtins, "__import__", no_fcntl)
        mp.delitem(sys.modules, "fcntl", raising=False)
        importlib.reload(ledger_module)
        assert ledger_module.fcntl is None
    importlib.reload(ledger_module)
    if sys.platform == "win32":
        # Windows has no fcntl at all: the fallback is the platform's
        # native state, before and after the reload.
        assert ledger_module.fcntl is None
    else:
        assert ledger_module.fcntl is not None
