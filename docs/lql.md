# LQL — the Ledger Query Language

LQL is the ledger's small, read-only query language (DESIGN-13
section 5). It is deliberately tiny: the whole grammar is on this
page. Anything outside the grammar is a parse error naming the
character position — parsing finishes before anything executes,
and LQL has no writes at all. Every construct compiles to a core
API call and returns exactly that call's result.

Run it from Python (`ledger.query("...")`), the CLI
(`epistemic-ledger query <store> "..."`), or the MCP `query` tool.

## Constructs

```
CLAIM <id>                          one claim, full record
                                    (the get_claim result, or null)
CLAIMS [WHERE <filter>]             live claims (list_claims, filtered)
WHY <id>                            support ancestry (why)
DEPENDS <id>                        dependency closure (depends_on)
IMPACT <id> [STRUCTURAL]            dependents closure (impact)
IMPACT <id> PROPAGATED TO <number>  dry-run revision impact
AS_OF <timestamp> <query>           CLAIM, CLAIMS, EVENTS, or
                                    DECISIONS against the state at
                                    that transaction time
EVENTS [WHERE <filter>]             the audit log, filtered
DECISIONS [WHERE <filter>]          decision nodes, with basis sets
HEALTH                              the health report
```

Keywords are case-insensitive. Claim ids are the bare `C…` /
`D…` / `E…` identifiers the ledger issued. Timestamps are
ISO-8601 (a trailing `Z` is accepted). Strings are single-quoted;
a quote inside a string is written doubled (`'it''s'`).

## Filters

A filter is comparisons joined by `AND` / `OR` — `AND` binds
tighter, and there are no parentheses (the grammar budget is the
point). A comparison is `<field> <op> <value>` with `op` one of
`= != < <= > >=`.

| Construct | Fields |
| --- | --- |
| CLAIMS | `status`, `writer`, `tier` (the writer's trust tier), `kind` (score kind), `score`, `entrenchment`, `materiality`, `critical` (`true`/`false`) |
| EVENTS | `type`, `actor`, `t` |
| DECISIONS | `kind` (`decision` or `governance`), `actor`, `label` |

Numeric fields require numeric values, text fields compare as
text, and `critical` compares against `true` or `false`. A wrong
type or an unknown field is a parse error at that token.

## AS_OF semantics

`AS_OF` runs a query against transaction-time state:

- `CLAIM` / `CLAIMS` read the bitemporal claim versions in force
  at the timestamp (the `believed_at` state).
- `EVENTS` returns log events with `t` at or before the
  timestamp; `DECISIONS` likewise.
- Graph traversals (`WHY`, `DEPENDS`, `IMPACT`) and `HEALTH` are
  current-state only: `AS_OF` before them is a parse error, not a
  silent substitution of today's graph for yesterday's.

## Examples

```
CLAIMS WHERE score < 0.3 AND status = 'active'
IMPACT C9f31 PROPAGATED TO 0
AS_OF 2026-01-15T00:00:00+00:00 CLAIMS WHERE writer = 'amy'
EVENTS WHERE type = 'score_revision' AND actor = 'system'
DECISIONS WHERE kind = 'governance'
```
