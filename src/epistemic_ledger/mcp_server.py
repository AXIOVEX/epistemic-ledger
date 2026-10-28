"""MCP server for the living epistemic ledger (DESIGN-13 section 6).

A Model Context Protocol server over stdio, standard library
only: newline-delimited JSON-RPC 2.0, the MCP initialize /
tools/list / tools/call surface. Run it as

    epistemic-ledger-mcp <ledger-dir>

(or set EPISTEMIC_LEDGER_STORE). The server holds one Ledger open
for its lifetime. Tools are typed schemas, not free text, except
`query` (LQL, itself read-only). Write tools — assert_claim,
challenge, record_decision — pass through the same governed paths
as the Python API: a challenge issued here is the same revision
event as one issued from Python, in the same log.

Tool results are the core API results serialized as JSON, so for a
fixed scenario the MCP face, the CLI, and the Python API return
identical results (claim M1).
"""

import json
import os
import sys

from . import __version__
from .ledger import Ledger

PROTOCOL_VERSION = "2024-11-05"


def _schema(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_STR = {"type": "string"}
_NUM = {"type": "number"}
_INT = {"type": "integer"}

TOOLS = [
    {
        "name": "get_claim",
        "description": "The live record of one claim, or null.",
        "inputSchema": _schema({"claim_id": _STR}, ["claim_id"]),
    },
    {
        "name": "list_claims",
        "description": "Every live claim, ordered by claim_id.",
        "inputSchema": _schema({}),
    },
    {
        "name": "why",
        "description": "A claim's live support set with scores and kinds.",
        "inputSchema": _schema({"claim_id": _STR}, ["claim_id"]),
    },
    {
        "name": "depends_on",
        "description": "The full revisit closure of a claim: every claim depending on it.",
        "inputSchema": _schema({"claim_id": _STR}, ["claim_id"]),
    },
    {
        "name": "impact",
        "description": (
            "What rests on a claim (DESIGN-13 section 3). Structural "
            "mode returns the dependents closure with distances and "
            "paths; propagated mode dry-runs a revision to "
            "revised_score (default 0.0) and reports score movements "
            "and affected decisions."
        ),
        "inputSchema": _schema(
            {
                "claim_id": _STR,
                "mode": {"type": "string", "enum": ["structural", "propagated"]},
                "revised_score": _NUM,
                "max_depth": _INT,
                "max_results": _INT,
            },
            ["claim_id"],
        ),
    },
    {
        "name": "assert_claim",
        "description": "Enter a new conclusion with a prior credence. Returns the claim_id.",
        "inputSchema": _schema(
            {"statement": _STR, "prior": _NUM, "actor": _STR},
            ["statement", "prior"],
        ),
    },
    {
        "name": "challenge",
        "description": (
            "Challenge a claim to zero through the governed revision "
            "path (the same manual_score event as from Python): the "
            "score is revised to 0.0 and dependents re-derive. "
            "Returns the revision report."
        ),
        "inputSchema": _schema({"claim_id": _STR, "actor": _STR}, ["claim_id"]),
    },
    {
        "name": "record_decision",
        "description": (
            "Record a decision as a graph node resting on the given "
            "basis claims. The basis set is immutable once recorded."
        ),
        "inputSchema": _schema(
            {
                "label": _STR,
                "basis": {"type": "array", "items": _STR},
                "actor": _STR,
                "rationale": _STR,
            },
            ["label", "basis"],
        ),
    },
    {
        "name": "verify_store",
        "description": "Integrity check: log and projection agree. deep=true also re-verifies signed verdicts.",
        "inputSchema": _schema({"deep": {"type": "boolean"}}),
    },
    {
        "name": "health",
        "description": "The store's health report.",
        "inputSchema": _schema({}),
    },
    {
        "name": "kill_metrics",
        "description": "The five kill-criteria metrics.",
        "inputSchema": _schema({}),
    },
    {
        "name": "query",
        "description": "Run an LQL query (DESIGN-13 section 5). Read-only; malformed input is a parse error with a position.",
        "inputSchema": _schema({"text": _STR}, ["text"]),
    },
]


def _call_tool(ledger, name, args):
    if name == "get_claim":
        return ledger.get_claim(args["claim_id"])
    if name == "list_claims":
        return ledger.list_claims()
    if name == "why":
        return ledger.why(args["claim_id"])
    if name == "depends_on":
        return ledger.depends_on(args["claim_id"])
    if name == "impact":
        return ledger.impact(
            args["claim_id"],
            mode=args.get("mode", "structural"),
            revised_score=args.get("revised_score"),
            max_depth=args.get("max_depth"),
            max_results=args.get("max_results", 1000),
        )
    if name == "assert_claim":
        claim_id = ledger.assert_claim(
            args["statement"],
            args["prior"],
            actor=args.get("actor", "mcp"),
        )
        return {"claim_id": claim_id}
    if name == "challenge":
        return ledger.manual_score(
            args["claim_id"], 0.0, actor=args.get("actor", "mcp")
        )
    if name == "record_decision":
        decision_id = ledger.record_decision(
            args["label"],
            args["basis"],
            actor=args.get("actor", "mcp"),
            rationale=args.get("rationale"),
        )
        return {"decision_id": decision_id}
    if name == "verify_store":
        return ledger.verify(deep=bool(args.get("deep", False)))
    if name == "health":
        return ledger.health()
    if name == "kill_metrics":
        return ledger.kill_metrics()
    if name == "query":
        return ledger.query(args["text"])
    raise KeyError(f"unknown tool {name!r}")


class McpServer:
    """One Ledger, one stdio stream. handle() maps a parsed
    JSON-RPC request to a response dict (or None for
    notifications), so the protocol logic is testable without a
    subprocess."""

    def __init__(self, ledger):
        self.ledger = ledger

    def handle(self, request):
        if not isinstance(request, dict):
            return _error(None, -32600, "invalid request")
        method = request.get("method")
        req_id = request.get("id")
        if method == "initialize":
            return _result(
                req_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "epistemic-ledger",
                        "version": __version__,
                    },
                },
            )
        if method == "ping":
            return _result(req_id, {})
        if method == "tools/list":
            return _result(req_id, {"tools": TOOLS})
        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            try:
                value = _call_tool(self.ledger, name, args)
                text = json.dumps(value, default=str)
                return _result(
                    req_id,
                    {"content": [{"type": "text", "text": text}], "isError": False},
                )
            except Exception as exc:
                return _result(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": f"error: {type(exc).__name__}: {exc}",
                            }
                        ],
                        "isError": True,
                    },
                )
        if req_id is None:
            return None  # a notification; nothing to answer
        return _error(req_id, -32601, f"method not found: {method}")


def _result(req_id, value):
    return {"jsonrpc": "2.0", "id": req_id, "result": value}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def serve(ledger, instream, outstream):
    server = McpServer(ledger)
    for line in instream:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            response = _error(None, -32700, "parse error")
            outstream.write(json.dumps(response) + "\n")
            outstream.flush()
            continue
        response = server.handle(request)
        if response is not None:
            outstream.write(json.dumps(response) + "\n")
            outstream.flush()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    store = argv[0] if argv else os.environ.get("EPISTEMIC_LEDGER_STORE")
    if not store:
        print(
            "usage: epistemic-ledger-mcp <ledger-dir> (or set EPISTEMIC_LEDGER_STORE)",
            file=sys.stderr,
        )
        return 2
    ledger = Ledger(store)
    try:
        serve(ledger, sys.stdin, sys.stdout)
    finally:
        ledger.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
