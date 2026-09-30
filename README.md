# Epistemic Ledger

> A living epistemic scoring system where every conclusion lives in an append-only database with a fluid certainty score, and new facts automatically trigger re-evaluation of the conclusions — and their dependents — that they affect, instead of any judgment ever being final.

Databases are deeply flawed: there is no built-in way to keep challenging the data, to know how true any of it is, or to update it as the evidence comes in. The epistemic ledger is an attempt to fix that — an append-only epistemic database over which an active feedback loop runs, so records are never destroyed but certainty stays fluid, and the system corrects itself, including its previously built structure.

## Status

**Research phase.** The foundations have been surveyed and framed; no implementation exists yet. See [`docs/PAPER.md`](docs/PAPER.md) for the full framing paper and [`docs/research/`](docs/research/) for the raw research notes with provenance.

## The idea in brief

1. **Append-only records.** Conclusions are never mutated or deleted. Corrections are new records that supersede old ones — the full history of what was believed, and when, stays queryable.
2. **Fluid certainty scores.** Every conclusion carries a score that moves as evidence accumulates — today's posterior is tomorrow's prior — rather than a one-time binary verdict.
3. **Dependency-tracked revisits.** Each conclusion records *why* it is held. When a new fact arrives, the system propagates the change along the dependency graph and re-evaluates exactly the conclusions it touches, plus their dependents.
4. **A trigger discipline.** Not every new fact warrants a revisit. The system needs a principled answer to *when* — from coarse dirty-flagging up through precise invalidation to judgmental materiality thresholds.

## Research foundations

Eight threads were surveyed to frame the design (canonical references in [`docs/PAPER.md`](docs/PAPER.md)):

| # | Thread | What it gives the ledger |
|---|--------|--------------------------|
| 1 | Bitemporal data modeling | Valid time vs. transaction time; retroactive correction without mutation |
| 2 | Belief revision (AGM) | Minimal-change revision; epistemic entrenchment as the "what to give up" rule |
| 3 | Truth maintenance (JTMS/ATMS) | Justification-tracked beliefs; dependency-directed retraction |
| 4 | Event sourcing | Append-only log; state as replay; compensating events |
| 5 | Incremental recomputation | Invalidation propagation; early cutoff; DBSP's formal delta theory |
| 6 | Change-impact analysis | The trigger problem: dirty flags → precise invalidation → materiality |
| 7 | Non-binary epistemic scoring | Sequential Bayes; Jeffrey kinematics for uncertain evidence |
| 8 | LLM memory & context cleanup | Offline consolidation; RAG freshness; bitemporal knowledge graphs |

The closest existing system to the whole: **Zep/Graphiti**-style bitemporal knowledge graphs (event time + ingestion time per edge, non-lossy retroactive correction).

## Why this matters beyond one project

The same machinery answers a pressing LLM problem: **context cleanup**. Retrieval freshness, offline memory consolidation, and principled invalidation of stale context are exactly the ledger's operations applied to an agent's working memory. Whatever is built here generalizes.

## Repository layout

```
.
├── README.md            # This file
├── LICENSE              # All rights reserved, © 2026 Axiovex Systems, LLC
├── docs/
│   ├── PAPER.md         # The framing paper
│   ├── DESIGN-01-record-schema-scoring.md  # Design memo 01 (record schema + scoring)
│   └── research/        # Raw research notes with provenance (2026-09-30)
├── prototype/           # v0.1 prototype (stdlib-only Python)
│   ├── ledger.py        # Core: event log, bitemporal store, revisit loop, queries
│   ├── demo.py          # End-to-end scenario
│   └── tests/           # Test suite
└── .gitignore
```

## Prototype v0.1

A working implementation of Design Memo 01's §8 scope lives in [`prototype/`](prototype/): append-only JSONL event log, SQLite bitemporal claim table, Jeffrey-update revisit loop with early cutoff, one materiality rule, the four queries (`BELIEVED_AT` / `CHANGED` / `DEPENDS_ON` / `WHY`), and all five kill criteria instrumented from day one.

```bash
cd prototype
python demo.py            # end-to-end scenario
python -m pytest tests/   # 10 tests, all green
```

## License

All rights reserved. © 2026 Axiovex Systems, LLC. See [LICENSE](LICENSE).
