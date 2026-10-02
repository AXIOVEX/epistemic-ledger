# CHURN-01 — Conflict-normalized churn calibration

**Date:** 2026-10-02. **Design:** DESIGN-09. **Script:**
`prototype/validation/churn_check.py`.

## Question

NEWSROOM-01 finding 3: raw churn (delta sign-changes per 10
revisions) fires on healthy adversarial tracking. Can a normalized
variant separate healthy tracking from instability?

## What was tried

1. **Travel normalization** (reversals per unit Σ|delta|): FAILED
   to separate. Per-report Bayesian updates move scores 0.003–0.1,
   so healthy claims and synthetic jitter both show travel ≤ 1.0
   over the window and normalize to their raw values (9.00 = 9.00).
2. **Materiality hysteresis** (adopted): count only reversals
   among moves ≥ the claim's materiality (0.05), over the aligned
   last-10-revision window.

## Results

| workload | raw | material |
|---|---|---|
| newsroom seed 0 | 8 | 3 |
| newsroom seed 1 | 7 | 2 |
| newsroom seed 2 | 8 | 5 |
| newsroom seed 3 | 8 | 4 |
| newsroom seed 4 | 9 | 7 |
| jitter-A, direct ±0.02 ×20 | 9 | 0 |
| jitter-B, propagated (combo parents ±0.04) | 9 | 0 |
| oscillation 0.3 ↔ 0.7 ×20 | 9 | 9 |
| big-swing 0.15 ↔ 0.85 ×20 | 9 | 9 |

## Verdict

Bar `max_material_churn = 8` replaces `max_churn` as the gate.
Separation is real but the healthy margin is one point (seed 4 at
7): the gate deliberately trips only on near-total position
instability. Trajectory inspection (F9, F11-wire) shows why no
tighter per-claim bar is honest — near the 0/1 boundaries a single
strong report (λ ≈ 6 in odds) is a material move, so a claim under
genuine adversarial fire legitimately posts 5–7. Integrator quality
below total instability is policed by Brier against outcomes, not
by churn. Raw churn remains reported, ungated, as a diagnostic.
