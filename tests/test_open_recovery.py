"""Crash recovery at open (DESIGN-16 S1c).

Opening a Python-engine store repairs the states a killed writer can
leave and refuses states a crash cannot produce:

- a torn final log line (the append never completed) is truncated;
- a projection that disagrees with the log — in either direction —
  is rebuilt from the log, which is ground truth;
- anything a rebuild cannot reconcile (a complete but unparseable
  log line is corruption, not a torn write) refuses the open loudly,
  while Ledger(path, recover=False) still opens for inspection.
"""

from __future__ import annotations

import os

import pytest

from epistemic_ledger.ledger import Ledger


def _store(tmp_path):
    led = Ledger(str(tmp_path))
    cid = led.assert_claim("alpha", 0.5)
    led.close()
    return cid


def test_clean_open_reports_no_repair(tmp_path):
    _store(tmp_path)
    led = Ledger(str(tmp_path))
    assert led.open_report["torn_bytes"] == 0
    assert led.open_report["rebuilt"] is False
    assert led.open_report["problems"] == []
    assert led.verify_store()["ok"]
    led.close()


def test_log_ahead_drift_rebuilt_at_open(tmp_path):
    cid = _store(tmp_path)
    led = Ledger(str(tmp_path), recover=False)
    led._emit(
        "assert",
        {
            "claim_id": "C-ghost01",
            "statement": "ghost",
            "prior": 0.4,
            "writer": None,
            "valid_from": None,
            "valid_to": None,
            "score_kind": "credence",
            "materiality": 0.05,
            "critical": False,
            "entrenchment": 0.5,
        },
        actor="system",
    )
    led.close()
    led = Ledger(str(tmp_path))
    assert led.open_report["rebuilt"] is True
    assert led.open_report["problems"]  # what was found, before repair
    assert led.verify_store()["ok"]
    assert led.get_claim("C-ghost01") is not None
    assert led.get_claim(cid) is not None
    led.close()


def test_projection_ahead_orphan_rebuilt_at_open(tmp_path):
    _store(tmp_path)
    led = Ledger(str(tmp_path))
    led.db.execute(
        """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                              valid_to, score, score_kind, status,
                              materiality, critical, entrenchment, writer)
           VALUES ('C-orphan9', '2026-01-01T00:00:00+00:00', 'orphan',
                   NULL, NULL, 0.9, 'credence', 'active', 0.05, 0, 0.5, NULL)"""
    )
    led.db.commit()
    led.close()
    led = Ledger(str(tmp_path))
    assert led.open_report["rebuilt"] is True
    assert led.get_claim("C-orphan9") is None
    assert led.verify_store()["ok"]
    led.close()


def test_torn_tail_truncated_at_open(tmp_path):
    cid = _store(tmp_path)
    with open(os.path.join(str(tmp_path), "events.jsonl"), "ab") as f:
        f.write(b'{"event_id": "E-torn", "t": "2026-01-01')
    led = Ledger(str(tmp_path))
    assert led.open_report["torn_bytes"] > 0
    assert led.open_report["rebuilt"] is False
    assert led.verify_store()["ok"]
    assert led.get_claim(cid) is not None
    led.close()


def test_complete_unparseable_line_refuses_recovering_open(tmp_path):
    _store(tmp_path)
    with open(os.path.join(str(tmp_path), "events.jsonl"), "a", encoding="utf-8") as f:
        f.write("{not json\n")
    with pytest.raises(RuntimeError):
        Ledger(str(tmp_path))
    # The inspection route still opens, and verify_store reports it.
    led = Ledger(str(tmp_path), recover=False)
    rep = led.verify_store()
    assert not rep["ok"]
    assert any("unparseable" in p for p in rep["problems"])
    led.close()


def test_missing_projection_rebuilt_at_open(tmp_path):
    cid = _store(tmp_path)
    os.remove(os.path.join(str(tmp_path), "ledger.db"))
    led = Ledger(str(tmp_path))
    assert led.open_report["rebuilt"] is True
    assert led.verify_store()["ok"]
    assert led.get_claim(cid) is not None
    led.close()
