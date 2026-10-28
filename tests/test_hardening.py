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
