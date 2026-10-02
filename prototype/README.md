# Prototype v0.1

Implements Design Memo 01 (`../docs/DESIGN-01-record-schema-scoring.md`), §8 scope:

- Append-only JSONL event log (`events.jsonl`) — the write model, ground truth.
- SQLite bitemporal claim table + bitemporal support edges (`ledger.db`) — the read model.
- Single credences; Jeffrey conditionalization for uncertain evidence.
- One support-edge revisit loop with early cutoff + materiality flags.
- Queries: `BELIEVED_AT` / `CHANGED` / `DEPENDS_ON` / `WHY`.
- The five kill criteria instrumented from day one (`kill_metrics()`).

Stdlib only. No dependencies, no network.

## Run

```bash
python demo.py            # end-to-end scenario
python -m pytest tests/  # test suite (run from this directory)
python stress/workload.py # trigger-discipline stress test (seeded epsilon sweep)
```

## Stress test

`stress/workload.py` builds a synthetic seeded workload (300 claims, 40 facts)
and sweeps the early-cutoff epsilon against an epsilon=0 oracle, measuring
trigger recall, precision, flag volume, and runtime. Findings are in
`../docs/TRIGGER-STRESS-01.md`. Current empirical defaults: epsilon=0.005,
materiality=0.05.

## v0.2: contradiction resolution

`declare_contradiction(a, b)` + `resolve_contradiction(id)`: entrenchment-ordered
contraction (Design Memo 02, `../docs/DESIGN-02-contradiction-resolution.md`).
Ties go to a human; the loser is Jeffrey-contracted against the winner and its
dependents re-propagate. Manual entrenchment tiers via `apply_tier`
(axiomatic/measured/inferred/provisional/deprecated); learned tiers deferred.

## v0.3: learned entrenchment, D–S intervals, context cleanup

- `learn_entrenchment()`: offline pass deriving entrenchment from calibration
  (1 − Brier against score-at-outcome-time); no data, no learning
  (`../docs/DESIGN-03-learned-entrenchment.md`).
- Opt-in Dempster–Shafer `[Bel, Pl]` intervals per claim with Dempster
  combination and refusal on pathological conflict; ignorance-gated abstention
  is the use-case that earns its keep (`../docs/DESIGN-04-ds-intervals.md`).
- `context/experiment.py`: ledger-backed vs frozen working memory on a
  flipping world — 70.6% of naive errors eliminated
  (`../docs/CONTEXT-CLEANUP-01.md`).

## Known v0.1 simplifications (documented, not hidden)

- Multi-supporter Jeffrey updates apply sequentially in edge order (naive).
- Entrenchment is stored per claim but conflict auto-resolution is deferred to v0.2.
- D–S intervals and imprecise probabilities are deferred per the memo.
- Kill-criterion bars are guesses; the audit sample for trigger recall is a hook, not a judge.
