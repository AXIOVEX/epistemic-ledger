"""The MCP face (DESIGN-13 section 6).

Claim M1: for a fixed scenario, the MCP tools, the CLI, and the
Python API return identical results. The scenario below runs the
same reads through all three faces — API directly, CLI in a
subprocess, MCP in a subprocess — on byte-identical copies of one
store, and diffs them. Write tools are exercised over MCP and
then read back through the API from the same log.
"""

import json
import os
import shutil
import subprocess
import sys

from epistemic_ledger import Ledger
from epistemic_ledger.cli import main as cli_main
from epistemic_ledger.mcp_server import McpServer


def _scenario_store(path):
    led = Ledger(path)
    a = led.assert_claim("alpha", 0.9)
    b = led.assert_claim("beta", 0.4)
    led.add_support(b, a, "evidential", p_given=0.95, p_given_not=0.05)
    did = led.record_decision("ship decision", [b])
    led.close()
    return a, b, did


class _McpClient:
    """A minimal stdio MCP client driving the real server process."""

    def __init__(self, store):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "epistemic_ledger.mcp_server", store],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        self._id = 0
        init = self.request("initialize", {})
        assert init["result"]["serverInfo"]["name"] == "epistemic-ledger"
        self.notify("notifications/initialized")

    def request(self, method, params):
        self._id += 1
        self.proc.stdin.write(
            json.dumps(
                {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
            )
            + "\n"
        )
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def notify(self, method):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method}) + "\n")
        self.proc.stdin.flush()

    def call(self, name, arguments=None):
        resp = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        result = resp["result"]
        assert result["isError"] is False, result["content"]
        return json.loads(result["content"][0]["text"])

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


def test_mcp_tools_in_process(tmp_path):
    store = str(tmp_path / "store")
    a, b, did = _scenario_store(store)
    led = Ledger(store)
    server = McpServer(led)
    listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {
        "get_claim",
        "list_claims",
        "why",
        "depends_on",
        "impact",
        "assert_claim",
        "challenge",
        "record_decision",
        "verify_store",
        "health",
        "kill_metrics",
        "query",
    }

    def call(name, args=None):
        resp = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": name, "arguments": args or {}},
            }
        )
        result = resp["result"]
        assert result["isError"] is False, result["content"]
        return json.loads(result["content"][0]["text"])

    assert call("get_claim", {"claim_id": a}) == led.get_claim(a)
    assert call("why", {"claim_id": b}) == led.why(b)
    assert call("impact", {"claim_id": a}) == led.impact(a)
    assert call("health") == led.health()
    assert call("query", {"text": f"CLAIM {a}"}) == led.query(f"CLAIM {a}")
    # A tool error is reported in-band, not raised through the server.
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "impact", "arguments": {"claim_id": "Cmissing"}},
        }
    )
    assert resp["result"]["isError"] is True
    led.close()


def test_m1_three_faces_identical(tmp_path):
    src = str(tmp_path / "src")
    a, b, did = _scenario_store(src)

    # Face 1: the Python API on the original.
    led = Ledger(src)
    api = {
        "health": led.health(),
        "impact": led.impact(a),
        "claims": led.query("CLAIMS WHERE score > 0.5"),
        "get_claim": led.get_claim(a),
    }
    led.close()

    # Face 2: the CLI on a byte-identical copy.
    cli_dir = str(tmp_path / "cli")
    shutil.copytree(src, cli_dir)
    import io
    from contextlib import redirect_stdout

    def run_cli(argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cli_main(argv)
        assert rc == 0
        return json.loads(buf.getvalue())

    cli = {
        "health": run_cli(["health", cli_dir]),
        "impact": run_cli(["impact", cli_dir, a]),
        "claims": run_cli(["query", cli_dir, "CLAIMS WHERE score > 0.5"]),
        "get_claim": run_cli(["query", cli_dir, f"CLAIM {a}"]),
    }
    assert cli == api

    # Face 3: MCP over stdio on another byte-identical copy.
    mcp_dir = str(tmp_path / "mcp")
    shutil.copytree(src, mcp_dir)
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        os.path.join(os.path.dirname(__file__), "..", "src")
        + os.pathsep
        + env.get("PYTHONPATH", "")
    )
    client = _McpClient.__new__(_McpClient)
    client.proc = subprocess.Popen(
        [sys.executable, "-m", "epistemic_ledger.mcp_server", mcp_dir],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    client._id = 0
    init = client.request("initialize", {})
    assert init["result"]["serverInfo"]["name"] == "epistemic-ledger"
    mcp = {
        "health": client.call("health"),
        "impact": client.call("impact", {"claim_id": a}),
        "claims": client.call("query", {"text": "CLAIMS WHERE score > 0.5"}),
        "get_claim": client.call("get_claim", {"claim_id": a}),
    }
    assert mcp == api

    # Write tools over MCP land in the same governed log.
    new = client.call("assert_claim", {"statement": "delta", "prior": 0.6})
    client.call("record_decision", {"label": "via mcp", "basis": [new["claim_id"]]})
    client.call("challenge", {"claim_id": new["claim_id"]})
    assert client.call("get_claim", {"claim_id": new["claim_id"]})["score"] == 0.0
    client.close()

    led = Ledger(mcp_dir)
    assert led.get_score(new["claim_id"]) == 0.0
    assert any(d["label"] == "via mcp" for d in led.decisions())
    led.close()
