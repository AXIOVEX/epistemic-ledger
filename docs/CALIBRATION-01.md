# CALIBRATION-01 — Agent tempering: a measured negative

**Date:** 2026-10-02. **Status:** complete; no change adopted.
Results: `prototype/validation/calibration_results.json`.
Harness: `prototype/validation/calibration.py` (selection rule
fixed in its docstring before any run).

## The question

NEWSROOM-01's known blemish: seed 2 tripped the Brier kill bar
(0.29 > 0.25) at ~83% accuracy, attributed at the time to the
agents' aggressive per-report likelihood ratios (learned accuracy
~0.9 ⇒ λ ≈ 9 per report). The proposed fix was tempering:
raise each report's λ to a power < 1 (temperature scaling on the
agent's evidence integration). Both agents in a trial share the
temper, keeping the ledger-vs-naive comparison fair.

## Protocol

Dev sweep: tempers {1.0, 0.75, 0.5, 0.35} × seeds 0–4 (the
published seeds), modeled extractor, 60 steps. Pre-stated
candidate rule: largest temper < 1.0 with worst-seed Brier ≤ 0.25,
mean ledger error no more than 0.005 worse than baseline, and
mean Brier strictly improved. A candidate would then face held-out
seeds 5–9 before adoption.

## Result

| temper | mean ledger err | mean Brier | worst-seed Brier |
|---|---|---|---|
| **1.0 (baseline)** | **0.1452** | **0.1368** | **0.2501** |
| 0.75 | 0.1675 | 0.1533 | 0.2740 |
| 0.5 | 0.2044 | 0.1710 | 0.2731 |
| 0.35 | 0.2258 | 0.1895 | 0.2834 |

Tempering degrades **every** metric monotonically. No candidate
met the dev rule; per protocol the held-out phase never ran and
**temper stays 1.0**. (Baseline mean ledger error 0.1452
reproduces NEWSROOM-01's 0.145 — the harness is the published
one, unchanged.)

## Interpretation

The λ-overconfidence diagnosis was wrong at the agent level.
Tempering does not merely soften confidence; it slows all
learning — trust convergence and fact tracking alike — and both
accuracy and Brier pay for it. Meanwhile the agents' fact
posteriors were never the problem: NEWSROOM-01's fact-claim Brier
diagnostic was 0.062. The kill-bar Brier is a whole-ledger metric
over heterogeneous claims (facts, desk assessments, derived
claims) recorded at sparse outcome times; its seed-2 excursion is
a property of a hard seed and the metric's composition, not a
defect with a temperature knob. The bar stays as an alarm, the
excursion stays on the record, and the "fix" is refuted — which
is what the alarm is for.
