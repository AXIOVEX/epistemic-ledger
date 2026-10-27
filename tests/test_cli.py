"""Tests for the command-line interface."""

import json

from epistemic_ledger import Ledger
from epistemic_ledger.cli import main


def test_cli_demo_runs(capsys):
    assert main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "day 1" in out and "kill metrics" in out


def test_cli_verify_clean_store(tmp_path, capsys):
    d = str(tmp_path / "ledger")
    L = Ledger(d)
    L.assert_claim("a claim", 0.5)
    L.close()
    assert main(["verify", d]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True


def test_cli_verify_unopenable_store_is_usage_error(tmp_path, capsys):
    # A path that cannot be a ledger directory (a file sits in the way)
    # must be a clean usage error, not a traceback. (Note: opening a
    # merely-missing path is not an error — the Ledger creates a fresh
    # store there, by design.)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    rc = main(["verify", str(blocker / "ledger")])
    assert rc == 2


def test_cli_kill_metrics(tmp_path, capsys):
    d = str(tmp_path / "ledger")
    L = Ledger(d)
    c = L.assert_claim("scored claim", 0.7)
    L.record_outcome(c, True)
    L.close()
    assert main(["kill-metrics", d]) == 0
    result = json.loads(capsys.readouterr().out)
    assert "brier" in result and "churn" in result
