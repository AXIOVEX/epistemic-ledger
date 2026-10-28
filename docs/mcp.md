# MCP server

`epistemic-ledger-mcp` serves the ledger to AI agents over the
Model Context Protocol (DESIGN-13 section 6): JSON-RPC 2.0 over
stdio, standard library only, no extra dependencies.

```
epistemic-ledger-mcp <ledger-dir>
# or set EPISTEMIC_LEDGER_STORE
```

The server holds one ledger open for its lifetime (the store is
single-writer, so one server per store). Tool results are the
core API results serialized as JSON — for a fixed scenario, the
MCP tools, the CLI, and the Python API return identical results
(claim M1, exercised in CI).

## Tools

| Tool | Arguments | Result |
| --- | --- | --- |
| `get_claim` | `claim_id` | the claim record, or null |
| `list_claims` | — | every live claim |
| `why` | `claim_id` | the claim's support set |
| `depends_on` | `claim_id` | the revisit closure |
| `impact` | `claim_id`, `mode`, `revised_score`, `max_depth`, `max_results` | the section-3 impact report |
| `assert_claim` | `statement`, `prior`, `actor` | the new `claim_id` |
| `challenge` | `claim_id`, `actor` | the revision report |
| `record_decision` | `label`, `basis`, `actor`, `rationale` | the new `decision_id` |
| `verify_store` | `deep` | the verification report |
| `health` | — | the health report |
| `kill_metrics` | — | the five kill metrics |
| `query` | `text` | the LQL result |

Inputs are typed schemas, not free text — except `query`, whose
text is LQL: itself read-only, with parse errors that name the
position.

Write tools (`assert_claim`, `challenge`, `record_decision`)
pass through the same governed paths as the Python API: a
challenge issued over MCP is the same revision event, in the
same log, as one issued from Python. A challenge revises the
claim's score to 0.0 and re-derives its dependents — it is a
real revision, not a flag; use `impact` with
`mode: "propagated"` first if you want the dry run.
