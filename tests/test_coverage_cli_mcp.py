"""Coverage tests for the CLI, the MCP server, and package init.

These exercise the command branches and protocol paths the
scenario tests in test_cli.py / test_mcp.py do not reach: the
migrate / pattern / snapshot / chained-health CLI routes and
their failure exits, the propagated impact and error exits of
the shared-open commands, every MCP tool dispatch, the stdio
serve loop, the MCP main() entry points, and the
PackageNotFoundError fallback for __version__.
"""

import io
import json
import runpy
import sqlite3
import sys

import pytest

import epistemic_ledger
import epistemic_ledger.migrate as migrate_mod
import epistemic_ledger.snapshots as snapshots_mod
from epistemic_ledger import Ledger
from epistemic_ledger.cli import main as cli_main
from epistemic_ledger.mcp_server import McpServer, serve
from epistemic_ledger.mcp_server import main as mcp_main


def _store(tmp_path, name="ledger"):
    d = str(tmp_path / name)
    led = Ledger(d)
    a = led.assert_claim("alpha claim", 0.9)
    b = led.assert_claim("beta claim", 0.4)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    led.close()
    return d, a, b


def _tampered_store(tmp_path, name="ledger"):
    """A store whose projection disagrees with its log, so
    verify_store() and health() both report ok=False."""
    d, a, b = _store(tmp_path, name)
    db = sqlite3.connect(str(tmp_path / name / "ledger.db"))
    db.execute(
        """INSERT INTO claims(claim_id, txn_from, statement, valid_from,
                              valid_to, score, score_kind, status,
                              materiality, critical, entrenchment, writer)
           VALUES (?, ?, ?, NULL, NULL, ?, 'credence', 'active',
                   0.05, 0, 0.5, NULL)""",
        ("C-orphan01", "2026-01-01T00:00:00+00:00", "planted claim", 0.9),
    )
    db.commit()
    db.close()
    return d


def _call(server, name, args=None, req_id=99):
    return server.handle(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        }
    )


def _call_ok(server, name, args=None):
    resp = _call(server, name, args)
    result = resp["result"]
    assert result["isError"] is False, result["content"]
    return json.loads(result["content"][0]["text"])


# ----------------------------------------------------------------------
# CLI: migrate
# ----------------------------------------------------------------------


def test_cli_migrate_success(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        migrate_mod,
        "migrate_store",
        lambda src, dst: {"migrated": 3, "src": src, "dst": dst},
    )
    rc = cli_main(["migrate", str(tmp_path / "old"), str(tmp_path / "new")])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["migrated"] == 3


def test_cli_migrate_failure_is_usage_error(tmp_path, capsys):
    rc = cli_main(["migrate", str(tmp_path / "missing-src"), str(tmp_path / "new")])
    assert rc == 2
    assert "migration failed" in capsys.readouterr().err


# ----------------------------------------------------------------------
# CLI: pattern commands
# ----------------------------------------------------------------------


def test_cli_pattern_validate_ok(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    assert cli_main(["pattern-validate", d]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is True
    assert report["coverage"]["claims"] == 2


def test_cli_pattern_validate_not_ok(tmp_path, capsys):
    d = tmp_path / "bad-ledger"
    d.mkdir()
    event = {
        "type": "assert",
        "payload": {"claim_id": "Cx", "statement": "x", "prior": 7},
    }
    (d / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    assert cli_main(["pattern-validate", str(d)]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert report["problems"]


def test_cli_pattern_commands_unreadable_log_is_usage_error(tmp_path, capsys):
    d = tmp_path / "broken-ledger"
    d.mkdir()
    (d / "events.jsonl").write_text("this is not json\n", encoding="utf-8")
    assert cli_main(["pattern-validate", str(d)]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_pattern_export_then_check_ok(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    out_dir = str(tmp_path / "pattern")
    assert cli_main(["pattern-export", d, out_dir]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["written"] == ["map.json", "map.md", "matrix.json", "matrix.md"]
    for name in report["written"]:
        assert (tmp_path / "pattern" / name).exists()
    assert cli_main(["pattern-check", d, out_dir]) == 0
    check = json.loads(capsys.readouterr().out)
    assert check == {"ok": True, "problems": []}


def test_cli_pattern_check_missing_files(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    empty = tmp_path / "empty-pattern"
    empty.mkdir()
    assert cli_main(["pattern-check", d, str(empty)]) == 1
    check = json.loads(capsys.readouterr().out)
    assert check["ok"] is False
    assert len(check["problems"]) == 4
    assert all(p.endswith(": missing") for p in check["problems"])


def test_cli_pattern_check_diverged_file(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    out_dir = tmp_path / "pattern"
    assert cli_main(["pattern-export", d, str(out_dir)]) == 0
    capsys.readouterr()
    (out_dir / "matrix.json").write_bytes(b"{}")
    assert cli_main(["pattern-check", d, str(out_dir)]) == 1
    check = json.loads(capsys.readouterr().out)
    assert check["ok"] is False
    assert any("matrix.json" in p and "diverges" in p for p in check["problems"])


# ----------------------------------------------------------------------
# CLI: snapshot / restore
# ----------------------------------------------------------------------


def test_cli_snapshot_refuses_legacy_store(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    rc = cli_main(["snapshot", d, str(tmp_path / "bundle")])
    assert rc == 2
    assert "migrate it first" in capsys.readouterr().err


def test_cli_snapshot_success(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        snapshots_mod,
        "snapshot_store",
        lambda src, dst: {"snapshot": "ok", "store": src},
    )
    store = tmp_path / "chained"
    store.mkdir()
    rc = cli_main(["snapshot", str(store), str(tmp_path / "bundle")])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["snapshot"] == "ok"


def test_cli_restore_success(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        snapshots_mod,
        "restore_snapshot",
        lambda src, dst: {"restored": True},
    )
    rc = cli_main(["restore", str(tmp_path / "bundle"), str(tmp_path / "new")])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["restored"] is True


def test_cli_snapshot_failure_is_usage_error(tmp_path, capsys, monkeypatch):
    def boom(src, dst):
        raise RuntimeError("bundle corrupt")

    monkeypatch.setattr(snapshots_mod, "snapshot_store", boom)
    store = tmp_path / "chained"
    store.mkdir()
    rc = cli_main(["snapshot", str(store), str(tmp_path / "bundle")])
    assert rc == 2
    assert "snapshot failed" in capsys.readouterr().err


def test_cli_restore_failure_is_usage_error(tmp_path, capsys, monkeypatch):
    def boom(src, dst):
        raise RuntimeError("no such bundle")

    monkeypatch.setattr(snapshots_mod, "restore_snapshot", boom)
    rc = cli_main(["restore", str(tmp_path / "bundle"), str(tmp_path / "new")])
    assert rc == 2
    assert "restore failed" in capsys.readouterr().err


# ----------------------------------------------------------------------
# CLI: health on a chained (Rust) store
# ----------------------------------------------------------------------


class _FakeCore:
    def health_json(self, path, arg):
        return json.dumps({"format": "chained", "ok": True, "path": path})


def test_cli_health_chained_store(tmp_path, capsys, monkeypatch):
    store = tmp_path / "chained"
    store.mkdir()
    (store / "events.log").write_text("", encoding="utf-8")
    monkeypatch.setattr(snapshots_mod, "_require_core", lambda: _FakeCore())
    assert cli_main(["health", str(store)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["format"] == "chained"
    assert report["ok"] is True


def test_cli_health_chained_store_failure(tmp_path, capsys, monkeypatch):
    store = tmp_path / "chained"
    store.mkdir()
    (store / "events.log").write_text("", encoding="utf-8")

    def boom():
        raise ImportError("core missing")

    monkeypatch.setattr(snapshots_mod, "_require_core", boom)
    assert cli_main(["health", str(store)]) == 2
    assert "health failed" in capsys.readouterr().err


# ----------------------------------------------------------------------
# CLI: shared-open commands, remaining branches and exits
# ----------------------------------------------------------------------


def test_cli_verify_not_ok_returns_1(tmp_path, capsys):
    d = _tampered_store(tmp_path)
    assert cli_main(["verify", d]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False


def test_cli_health_ledger_store(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    assert cli_main(["health", d]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["format"] == "0.12-jsonl"


def test_cli_health_not_ok_returns_1(tmp_path, capsys, monkeypatch):
    # A damaged-projection store cannot be used here: health is a
    # working open (recover=True), which rebuilds the projection
    # and repairs exactly that damage before health() runs. Stub
    # the report instead; the branch under test is the CLI's
    # ok -> exit-code mapping.
    d, a, b = _store(tmp_path)
    monkeypatch.setattr(
        Ledger,
        "health",
        lambda self: {"ok": False, "problems": ["planted problem"]},
    )
    assert cli_main(["health", d]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False


def test_cli_impact_propagated(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    rc = cli_main(["impact", d, a, "--propagated", "--to", "0.0"])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "propagated"


def test_cli_impact_propagated_default_to(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    rc = cli_main(["impact", d, a, "--propagated"])
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "propagated"


def test_cli_impact_unknown_claim_is_usage_error(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    assert cli_main(["impact", d, "Cmissing"]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_query_parse_error_is_usage_error(tmp_path, capsys):
    d, a, b = _store(tmp_path)
    assert cli_main(["query", d, "BOGUS !!!"]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli_main(["--version"])
    assert excinfo.value.code == 0
    assert "epistemic-ledger" in capsys.readouterr().out


def test_cli_module_main_guard(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["epistemic-ledger", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("epistemic_ledger.cli", run_name="__main__")
    assert excinfo.value.code == 0


def test_package_main_module(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["epistemic-ledger", "--version"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("epistemic_ledger", run_name="__main__")
    assert excinfo.value.code == 0


# ----------------------------------------------------------------------
# __init__: the PackageNotFoundError fallback for __version__
# ----------------------------------------------------------------------


def test_version_fallback_when_package_not_installed(monkeypatch):
    import importlib
    import importlib.metadata

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    try:
        reloaded = importlib.reload(epistemic_ledger)
        assert reloaded.__version__ == "0+unknown"
    finally:
        monkeypatch.undo()
        reloaded = importlib.reload(epistemic_ledger)
    assert reloaded.__version__ != "0+unknown"


# ----------------------------------------------------------------------
# MCP: tool dispatch
# ----------------------------------------------------------------------


@pytest.fixture
def mcp(tmp_path):
    d = str(tmp_path / "store")
    led = Ledger(d)
    a = led.assert_claim("alpha", 0.9)
    b = led.assert_claim("beta", 0.4)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    server = McpServer(led)
    yield server, led, a, b
    led.close()


def test_mcp_list_claims_and_depends_on(mcp):
    server, led, a, b = mcp
    claims = _call_ok(server, "list_claims")
    assert {c["claim_id"] for c in claims} == {a, b}
    assert _call_ok(server, "depends_on", {"claim_id": a}) == led.depends_on(a)
    assert _call_ok(server, "list_claims") == led.list_claims()


def test_mcp_assert_claim_tool(mcp):
    server, led, a, b = mcp
    out = _call_ok(server, "assert_claim", {"statement": "gamma", "prior": 0.3})
    assert led.get_claim(out["claim_id"])["statement"] == "gamma"
    out2 = _call_ok(
        server,
        "assert_claim",
        {"statement": "delta", "prior": 0.5, "actor": "tester"},
    )
    assert led.get_claim(out2["claim_id"]) is not None


def test_mcp_challenge_tool(mcp):
    server, led, a, b = mcp
    report = _call_ok(server, "challenge", {"claim_id": b})
    assert "new" in report
    assert led.get_score(b) == 0.0


def test_mcp_record_decision_tool(mcp):
    server, led, a, b = mcp
    out = _call_ok(
        server,
        "record_decision",
        {"label": "ship it", "basis": [b], "rationale": "because"},
    )
    assert any(
        dec["decision_id"] == out["decision_id"] and dec["label"] == "ship it"
        for dec in led.decisions()
    )


def test_mcp_verify_store_tool(mcp):
    server, led, a, b = mcp
    assert _call_ok(server, "verify_store") == led.verify()
    deep = _call_ok(server, "verify_store", {"deep": True})
    assert deep == led.verify(deep=True)
    assert "verdict_signatures" in deep


def test_mcp_kill_metrics_tool(mcp):
    server, led, a, b = mcp
    assert _call_ok(server, "kill_metrics") == led.kill_metrics()


def test_mcp_impact_propagated_tool(mcp):
    server, led, a, b = mcp
    out = _call_ok(
        server,
        "impact",
        {"claim_id": a, "mode": "propagated", "revised_score": 0.0},
    )
    assert out == led.impact(a, mode="propagated", revised_score=0.0)


def test_mcp_unknown_tool_is_error(mcp):
    server, led, a, b = mcp
    resp = _call(server, "no_such_tool")
    assert resp["result"]["isError"] is True
    assert "KeyError" in resp["result"]["content"][0]["text"]


# ----------------------------------------------------------------------
# MCP: protocol handling
# ----------------------------------------------------------------------


def test_mcp_initialize(mcp):
    server, led, a, b = mcp
    resp = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2024-11-05"
    assert resp["result"]["serverInfo"]["name"] == "epistemic-ledger"
    assert resp["result"]["capabilities"] == {"tools": {}}


def test_mcp_ping(mcp):
    server, led, a, b = mcp
    resp = server.handle({"jsonrpc": "2.0", "id": 7, "method": "ping"})
    assert resp == {"jsonrpc": "2.0", "id": 7, "result": {}}


def test_mcp_non_dict_request_is_invalid(mcp):
    server, led, a, b = mcp
    for bad in (["not", "a", "dict"], "text", 42, None):
        resp = server.handle(bad)
        assert resp["id"] is None
        assert resp["error"]["code"] == -32600


def test_mcp_unknown_method_with_id(mcp):
    server, led, a, b = mcp
    resp = server.handle({"jsonrpc": "2.0", "id": 5, "method": "bogus/method"})
    assert resp["error"]["code"] == -32601
    assert "bogus/method" in resp["error"]["message"]


def test_mcp_notification_gets_no_response(mcp):
    server, led, a, b = mcp
    assert (
        server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    )
    assert server.handle({"method": "bogus/notification"}) is None


def test_mcp_tools_call_without_params(mcp):
    server, led, a, b = mcp
    resp = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call"})
    assert resp["result"]["isError"] is True


# ----------------------------------------------------------------------
# MCP: the stdio serve loop
# ----------------------------------------------------------------------


def test_mcp_serve_loop(tmp_path):
    d = str(tmp_path / "store")
    led = Ledger(d)
    led.assert_claim("alpha", 0.9)
    lines = [
        "",  # blank lines are skipped
        "   ",
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}),
        "not json at all",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ]
    out = io.StringIO()
    serve(led, io.StringIO("\n".join(lines) + "\n"), out)
    led.close()
    responses = [json.loads(line) for line in out.getvalue().splitlines()]
    # ping + parse error + tools/list answer; the notification does not.
    assert len(responses) == 3
    assert responses[0]["result"] == {}
    assert responses[1]["error"]["code"] == -32700
    assert "tools" in responses[2]["result"]


# ----------------------------------------------------------------------
# MCP: main() entry points
# ----------------------------------------------------------------------


def test_mcp_main_no_store_is_usage_error(monkeypatch, capsys):
    monkeypatch.delenv("EPISTEMIC_LEDGER_STORE", raising=False)
    assert mcp_main([]) == 2
    assert "usage:" in capsys.readouterr().err


def test_mcp_main_with_argv_store(tmp_path, monkeypatch):
    d, a, b = _store(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert mcp_main([d]) == 0


def test_mcp_main_with_env_store(tmp_path, monkeypatch):
    d, a, b = _store(tmp_path)
    monkeypatch.setenv("EPISTEMIC_LEDGER_STORE", d)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert mcp_main([]) == 0


def test_mcp_main_argv_none_uses_sys_argv(tmp_path, monkeypatch):
    d, a, b = _store(tmp_path)
    monkeypatch.setattr(sys, "argv", ["epistemic-ledger-mcp", d])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert mcp_main() == 0


def test_mcp_main_serves_requests(tmp_path, monkeypatch):
    d, a, b = _store(tmp_path)
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}) + "\n"
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdin", io.StringIO(request))
    monkeypatch.setattr(sys, "stdout", out)
    assert mcp_main([d]) == 0
    assert json.loads(out.getvalue())["result"] == {}


def test_mcp_module_main_guard(tmp_path, monkeypatch):
    d, a, b = _store(tmp_path)
    monkeypatch.setattr(sys, "argv", ["epistemic-ledger-mcp", d])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("epistemic_ledger.mcp_server", run_name="__main__")
    assert excinfo.value.code == 0
