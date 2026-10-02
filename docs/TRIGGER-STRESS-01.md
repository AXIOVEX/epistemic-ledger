# Trigger-Discipline Stress Test 01

**Date:** 2026-10-01. **Code:** `prototype/stress/workload.py` (seeded, reproducible).
**Scope:** Design Memo 01 §5/§8 — measure over/under-invalidation of the revisit loop's early cutoff; tune epsilon empirically.

## Method

Synthetic workload, seed 42: 300 claims in a random DAG (0–3 supporters each, from earlier claims), then a stream of 40 facts, each attached as an evidential supporter to 1–5 random claims with random likelihoods. For each fact, the revisit loop runs twice on two identically-seeded ledgers — once with the epsilon under test, once with epsilon=0 as the oracle. Ground truth: a claim *should* be revisited iff its true (oracle) |delta| >= materiality (0.05). Metrics: trigger recall, precision (1 − precision = over-invalidation), flag volume, wall time.

## Bug found by the harness (fixed)

The determinism self-check failed before any measurement: two identically-seeded runs produced different scores. Root cause — `_live_edges` had no `ORDER BY`, so SQLite served rows via the PK index ordered by random uuid `supports_id`, and the order-dependent sequential Jeffrey then produced different posteriors from identical evidence. An epistemic system that gives different answers from the same evidence is broken, so this was fixed before measuring: all edge/claim queries now `ORDER BY` (causal attachment order for edges). Lesson recorded: the stress harness earned its keep on day one.

## Results

| epsilon | recall | precision | mean flags | max flags | mean closure | wall (40 facts) |
|---------|--------|-----------|------------|-----------|--------------|-----------------|
| 0.000   | 1.000  | 0.709     | 17.8       | 51        | 26.9         | 0.54s           |
| 0.005   | 0.960  | 0.715     | 17.1       | 52        | 26.9         | 0.43s           |
| 0.010   | 0.948  | 0.742     | 16.8       | 52        | 26.9         | 0.45s           |
| 0.020   | 0.866  | 0.787     | 15.4       | 45        | 26.9         | 0.42s           |
| 0.050   | 0.757  | 0.919     | 14.5       | 56        | 26.9         | 0.40s           |

F1 is flat (~0.82–0.83) across the sweep: recall and precision trade almost linearly, with no sharp knee.

## Reading

- **Even with no cutoff, precision is only 0.71.** ~29% of closure claims move immaterially. The cutoff is doing real work, not premature optimization.
- **Recall loss compounds.** Cutoff doesn't just skip the small-delta claim — it perturbs downstream scores (dependents never see the skipped change), so recall falls faster than the naive "claims in [eps, materiality)" model predicts. This is the main cost of the cutoff and was not obvious before measuring.
- **Flag volume lands in the memo's band.** Mean ~17, median ~13 at eps=0.01 — squarely in the 8–15 heuristic. But the distribution is heavy-tailed (max 52): hub facts attached to well-connected claims flood review. Per-claim materiality tuning for hubs, and/or a top-k flag budget per cycle, is the follow-up.
- **Runtime is a non-issue at this scale:** ~10ms per fact for a 27-claim mean closure. The cutoff's value here is log/attention hygiene, not compute.

## Decision

**epsilon default: 0.005** (changed in code). A missed trigger is a silent staleness bug — the exact failure the ledger exists to prevent — while over-invalidation is cheap compute. So recall outranks precision: 0.005 keeps recall at 0.96 while cutting the worst waste. (0.01 at recall 0.948 is defensible; 0.005 is the asymmetry-adjusted pick.) **Materiality default stays 0.05** — flag volume validates the memo's heuristic.

## Limitations (honest)

- Synthetic workload: random DAG, uniform-ish likelihoods — not a real domain. Real support graphs may be denser, spikier, or cyclic (cycles untested).
- The oracle shares the system's naive-sequential Jeffrey; this measures the *cutoff's* effect, not update-rule correctness (that's the unit tests' job).
- Single-threaded, single-machine; no concurrency behavior measured.
- Kill-criterion bars remain guesses; this run instruments, it doesn't judge.
