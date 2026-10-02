# Epistemic Ledger

> A living epistemic scoring system where every conclusion lives in an append-only database with a fluid certainty score, and new facts automatically trigger re-evaluation of the conclusions — and their dependents — that they affect, instead of any judgment ever being final.

Databases are deeply flawed: there is no built-in way to keep challenging the data, to know how true any of it is, or to update it as the evidence comes in. The epistemic ledger is an attempt to fix that — an append-only epistemic database over which an active feedback loop runs, so records are never destroyed but certainty stays fluid, and the system corrects itself, including its previously built structure.

## Status

**Implemented and validated** (v0.11, 2026-10-02). The framing below became a working prototype: an event-sourced, bitemporal ledger with a dependency-propagated revisit loop, learned entrenchment, Dempster-Shafer intervals, joint likelihoods, contradiction detection and resolution, governance (writer tiers, signed verdicts, escalation, named-graph authority ceilings, predicate policies), an offline LLM consolidation pass, and a hardened single-writer store with integrity verification. See [`docs/PAPER.md`](docs/PAPER.md) for the framing paper, `docs/DESIGN-*.md` for the design memos, and `docs/research/` for the raw research notes with provenance.

Measured results so far, each with its own report in `docs/`:

- **Revision value** (CONTEXT-CLEANUP-01, REPO-HISTORY-VALIDATION): the revisit loop eliminates 70.6% of naive staleness errors on dependency chains, 62.8% with joint likelihoods, 81.0% on this repository's own git history.
- **Trigger discipline** (TRIGGER-STRESS-01): epsilon 0.005 balances recall 0.96 / precision 0.72; the cutoff earns its keep.
- **Adversarial newsroom** (NEWSROOM-01, LOCAL-EXTRACTION-01): against adversarial sources the ledger eliminates 20.8% (modeled extraction) to 22.2% (real LLM extraction, local Qwen3-8B, $0) of a frozen baseline's errors — 51-61% on derived claims.
- **Free prose** (FREETEXT-01): on authored non-template text the advantage thins to 16.8% / 43.5% derived and becomes seed-dependent; the report states the sensitivity plainly.
- **Independent prose** (INDIE-CORPUS-01): on text authored by a different model family (GPT-4.1), the advantage reproduces at 21.1% / 49.7% derived with a different failure anatomy — the authorship caveat is retired.
- **Kill bars** (KILL-BARS-01): every gate threshold re-measured across all workload families; two adjusted under a pre-stated rule, one held at its definitional value on the record.
- **LLM consolidation** (CONSOLIDATION-01, LOCAL-CONSOLIDATION-01): the offline pass matches frontier-model precision/recall locally at $0 — in its thinking configuration; the no-thinking configuration fails, measurably.
- **Churn and calibration** (CHURN-01, CALIBRATION-01): conflict-normalized material churn gates at 8; a proposed agent-tempering fix was tested and *refuted* — reported as a negative.

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
│   ├── DESIGN-01-record-schema-scoring.md  # Record schema + scoring calculus
│   ├── DESIGN-02-contradiction-resolution.md  # Entrenchment-ordered contraction
│   ├── DESIGN-03-learned-entrenchment.md   # Calibration-derived entrenchment
│   ├── DESIGN-04-ds-intervals.md           # D–S intervals: keep-or-cut verdict
│   ├── TRIGGER-STRESS-01.md  # Trigger-discipline stress test report
│   ├── CONTEXT-CLEANUP-01.md  # LLM context-cleanup experiment report
│   └── research/        # Raw research notes with provenance (2026-09-30)
│       └── BIBLIOGRAPHY.md  # Annotated bibliography: primary-source verification (2026-10-01)
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
