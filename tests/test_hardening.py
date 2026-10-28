"""Tests for the Ledger Standard v1 gap-assessment small fixes.

Queue items 1-3 (2026-10-27 gap assessment):

1. verify_store() must check the projection-to-log direction too:
   a projection row with no corresponding log event is a finding.
2. Verdict signatures must be verified against the key in force at
   signing time, not the signer's current key.
3. Lifecycle statuses entered-in-error / dead, and supersede()
   requiring a reason bundle (reason + actor + source).
"""

import shutil
import tempfile

import pytest

from epistemic_ledger import ed25519 as _ed
from epistemic_ledger.ledger import Ledger


@pytest.fixture
def ledger():
    d = tempfile.mkdtemp()
    L = Ledger(d)
    yield L
    L.close()  # Windows cannot delete a store whose files are still open
    shutil.rmtree(d)


# ----------------------------------------------------------------------
# Queue item 1: verify_store() reverse-direction (projection -> log)
# ----------------------------------------------------------------------


def test_verify_store_detects_projection_row_without_log_event(ledger):
    ledger.assert_claim("a real claim", 0.5)
    # Tamper: insert a live projection row directly in SQLite. There is
    # no assert event for this claim in the log, so the forward check
    # (log -> projection) cannot see it; the reverse check must.
    ledger.db.execute(
        """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                              valid_to, score, score_kind, status,
                              materiality, critical, entrenchment, writer)
           VALUES (?, ?, ?, NULL, NULL, ?, 'credence', 'active',
                   0.05, 0, 0.5, NULL)""",
        ("C-orphan01", "2026-01-01T00:00:00+00:00", "planted claim", 0.9),
    )
    ledger.db.commit()
    rep = ledger.verify_store()
    assert not rep["ok"]
    assert any("C-orphan01" in p for p in rep["problems"])


# ----------------------------------------------------------------------
# Queue item 2: verdict signatures verified against the key in force
# at signing time (the writers table is bitemporal)
# ----------------------------------------------------------------------

_SEED_K1 = bytes(range(32))
_SEED_K2 = bytes(range(32, 64))
_T1 = "2026-01-01T00:00:00+00:00"
_T2 = "2026-02-01T00:00:00+00:00"
_T3 = "2026-03-01T00:00:00+00:00"


def _held_contradiction(ledger, seed):
    """A held contradiction with a keyed owner, all at explicit times."""
    ledger.register_writer(
        "owner-1", "owner", t=_T1, public_key=_ed.publickey(seed).hex()
    )
    ledger.register_writer("contrib-1", "contributor", t=_T1)
    axiom = ledger.assert_claim("the axiom", 0.9, entrenchment=1.0, t=_T1)
    chal = ledger.assert_claim("the challenger", 0.8, entrenchment=0.5, t=_T1)
    held_id = ledger.declare_contradiction(axiom, chal, writer="contrib-1", t=_T1)
    assert len(ledger.held_contradictions()) == 1
    return held_id


def test_verdict_signed_before_rotation_still_audits_valid(ledger):
    held_id = _held_contradiction(ledger, _SEED_K1)
    msg = Ledger.verdict_message("escalate", held_id, "owner-1", "dismiss")
    ledger.escalate_contradiction(
        held_id,
        "dismiss",
        writer="owner-1",
        signature=_ed.sign(_SEED_K1, msg.encode()).hex(),
        t=_T2,
    )
    assert ledger.verify_verdict_signatures()["valid"] == 1
    # Rotate the owner's key. History signed under K1 must still audit
    # as valid: K1 was the key in force when the verdict was signed.
    ledger.register_writer(
        "owner-1", "owner", t=_T3, public_key=_ed.publickey(_SEED_K2).hex()
    )
    audit = ledger.verify_verdict_signatures()
    assert audit == {"checked": 1, "valid": 1, "invalid": []}


def test_verdict_signed_with_key_not_in_force_at_signing_time_fails(ledger):
    # K1 is in force in February; K2 only takes over in March.
    ledger.register_writer(
        "owner-1", "owner", t=_T1, public_key=_ed.publickey(_SEED_K1).hex()
    )
    ledger.register_writer(
        "owner-1", "owner", t=_T3, public_key=_ed.publickey(_SEED_K2).hex()
    )
    # A log entry timestamped February but signed with K2: K2 is the
    # signer's current key, but it was not in force at signing time,
    # so the audit must reject it (the old current-key audit accepted
    # exactly this). Written straight to the log, as a forged or
    # backdated entry would appear to an auditor.
    msg = Ledger.verdict_message("escalate", "E-held-x", "owner-1", "dismiss")
    ev = ledger._emit(
        "contradiction_dismissed",
        {
            "held_id": "E-held-x",
            "signer": "owner-1",
            "signature": _ed.sign(_SEED_K2, msg.encode()).hex(),
            "signed_message": msg,
        },
        actor="system",
        t=_T2,
    )
    audit = ledger.verify_verdict_signatures()
    assert audit["checked"] == 1 and audit["valid"] == 0
    assert audit["invalid"] == [ev["event_id"]]


# ----------------------------------------------------------------------
# Queue item 3: lifecycle statuses + the reason bundle on supersede()
# ----------------------------------------------------------------------


def test_supersede_requires_reason_bundle(ledger):
    c1 = ledger.assert_claim("old claim", 0.6, t=_T1)
    # No bundle at all: reason and source are required keyword args.
    with pytest.raises(TypeError):
        ledger.supersede(c1, "corrected claim", 0.8)
    # An empty reason is not a bundle either.
    with pytest.raises(ValueError):
        ledger.supersede(c1, "corrected claim", 0.8, reason="  ", source="audit-7")
    with pytest.raises(ValueError):
        ledger.supersede(
            c1, "corrected claim", 0.8, reason="typo in source data", source=""
        )
    # Nothing happened: the old claim is still live and active.
    assert ledger._live_claim(c1)["status"] == "active"


def test_supersede_event_carries_reason_bundle(ledger):
    c1 = ledger.assert_claim("old claim", 0.6, t=_T1)
    c2 = ledger.supersede(
        c1,
        "corrected claim",
        0.8,
        reason="source data had a typo",
        source="audit-7",
        actor="reviewer-1",
        t=_T2,
    )
    assert c1 != c2
    ev = [e for e in ledger._events() if e["type"] == "supersede"]
    assert len(ev) == 1
    assert ev[0]["actor"] == "reviewer-1"
    assert ev[0]["payload"]["old_claim_id"] == c1
    assert ev[0]["payload"]["new_claim_id"] == c2
    assert ev[0]["payload"]["reason"] == "source data had a typo"
    assert ev[0]["payload"]["source"] == "audit-7"
    # A clean supersede is a legitimate lifecycle end, not corruption:
    # the integrity check stays green.
    assert ledger.verify_store()["ok"]


def test_claim_can_be_marked_entered_in_error_and_dead(ledger):
    bad = ledger.assert_claim("entered by mistake", 0.4, t=_T1)
    stale = ledger.assert_claim("no longer applicable", 0.7, t=_T1)
    ledger.set_claim_status(
        bad,
        "entered-in-error",
        reason="duplicate of an existing claim",
        source="intake-review",
        actor="reviewer-1",
        t=_T2,
    )
    ledger.set_claim_status(
        stale,
        "dead",
        reason="the program it described was cancelled",
        source="ops-notice-12",
        actor="reviewer-1",
        t=_T2,
    )
    # Like a superseded claim, a terminal-status claim has no live
    # row; its final closed version carries the status.
    for cid, want in ((bad, "entered-in-error"), (stale, "dead")):
        assert ledger._live_claim(cid) is None
        closed = ledger.db.execute(
            "SELECT * FROM claims WHERE claim_id = ? AND txn_to IS NOT NULL",
            (cid,),
        ).fetchone()
        assert closed["status"] == want
    # The status changes are events in the log, carrying the bundle.
    evs = [e for e in ledger._events() if e["type"] == "claim_status_changed"]
    assert len(evs) == 2
    by_claim = {e["payload"]["claim_id"]: e for e in evs}
    assert by_claim[bad]["payload"]["status"] == "entered-in-error"
    assert by_claim[bad]["payload"]["reason"] == "duplicate of an existing claim"
    assert by_claim[bad]["payload"]["source"] == "intake-review"
    assert by_claim[bad]["actor"] == "reviewer-1"
    assert by_claim[stale]["payload"]["status"] == "dead"
    assert by_claim[stale]["payload"]["reason"] == (
        "the program it described was cancelled"
    )
    assert by_claim[stale]["payload"]["source"] == "ops-notice-12"
    # Terminal lifecycle ends are legitimate: the store still verifies.
    assert ledger.verify_store()["ok"]


def test_set_claim_status_guards(ledger):
    c = ledger.assert_claim("a claim", 0.5, t=_T1)
    # Only the two new terminal statuses go through this method:
    # 'active' is assert_claim's job, 'superseded' is supersede()'s.
    for bad_status in ("active", "superseded", "bogus"):
        with pytest.raises(ValueError):
            ledger.set_claim_status(c, bad_status, reason="r", source="s", t=_T2)
    with pytest.raises(TypeError):  # the bundle is required here too
        ledger.set_claim_status(c, "dead")
    with pytest.raises(KeyError):
        ledger.set_claim_status("C-nope", "dead", reason="r", source="s", t=_T2)
    assert ledger._live_claim(c)["status"] == "active"
