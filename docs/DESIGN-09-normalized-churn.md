# Design Memo 09 — Conflict-normalized churn

**Date:** 2026-10-02. **Status:** decided; implemented in
`prototype/ledger.py` `kill_metrics` / `check_kill_bars` (v0.8).

## Problem

Raw churn (kill_metrics §2) counts direction reversals in a claim's
recent score deltas. NEWSROOM-01 finding 3: healthy adversarial
tracking — an honest wire and an adversarial rumor pushing the same
claim in opposite directions — produces 4–9 reversals per 10
revisions, tripping the bar (seed 4) even though nothing is
unstable. The bar was widened 4 → 8 on that observation with a
recorded caveat: *do not widen again; build a conflict-normalized
metric instead.* This memo is that metric.

## Failed first attempt (recorded, not buried)

Normalization by gross travel — reversals per unit of Σ|delta| —
assumed healthy tracking rides on large opposing moves. Measured
against the actual newsroom ledgers it does not separate: per-report
Bayesian updates move scores by 0.003–0.1, so healthy claims and
synthetic jitter both show travel ≤ 1.0 over the window and
normalize to their raw values (healthy max 9.00 = jitter 9.00).
The assumption described a synthetic workload, not the real system.

## The normalizer that fits the measured system: materiality

The ledger already has a decision-relevance threshold: materiality
(default 0.05) — score movements below it change no flag, trigger,
or decision. Measured healthy conflict is exactly a sub-materiality
tug-of-war: balanced opposing reports (conflict_balance ≈ 0.9–1.0)
nudging the score ±0.01–0.05, occasionally accumulating into a real
move when the evidence genuinely shifts. Genuine instability —
a broken integrator, a feedback path, an evidence source with
absurd per-report weight (cf. NEWSROOM-01's overconfidence finding)
— shows up as repeated **material** moves in alternating
directions: the claim's *position* keeps flipping.

**Material churn**: over the same last-10-revision window as raw
churn, walk the claim's score trajectory with a hysteresis anchor.
When the score has moved ≥ the claim's materiality from the
anchor, record a material move (direction = sign of travel) and
reset the anchor there. Material churn = direction reversals among
the material moves in the window.

- Sub-materiality oscillation (jitter, propagated residue, balanced
  micro-tugs): zero material moves → churn 0. Absorbed, correctly —
  it cannot affect any decision the system makes.
- Healthy newsroom tracking: per-seed max 2–7 (measured, CHURN-01).
- Material oscillation (0.3 ↔ 0.7 alternation): 9 → trips.

## Bar change (explicit, not a widening)

`max_churn` is **superseded** as a kill bar by `max_material_churn`
= 8. Raw churn, gross travel, and conflict balance stay computed
and reported in `check_kill_bars` values — visible, ungated.

Calibration (CHURN-01, `prototype/validation/churn_check.py`,
aligned last-10-revision window):

| workload | raw | material |
|---|---|---|
| newsroom seed 0–4 (healthy worst, seed 4) | 9 | **7** |
| jitter, direct ±0.02 | 9 | 0 |
| jitter, propagated via combo parents | 9 | 0 |
| material oscillation 0.3 ↔ 0.7 | 9 | **9** |
| big-swing 0.15 ↔ 0.85 | 9 | **9** |

The gate trips only on near-total position instability (9 = every
material move in the window reverses). That is deliberate: below
that level, per-claim churn cannot distinguish a bad integrator
from a genuinely adversarial evidence stream — in this kernel all
score movement enters from outside, so the ledger audits its own
machinery (jitter, fanout, triggers) intrinsically, and integrator
quality is policed by the Brier bar against outcomes (NEWSROOM-01
seed 2's overconfidence tripped Brier, correctly).

Out of scope: the stability-decay path in `learn_entrenchment`
counts 0.5-crossings over full history — a different quantity with
a soft effect (capped, decay-only). Deliberately unchanged.
