# Design Memo 03 — Learned entrenchment

**Date:** 2026-10-01. **Status:** decided; implemented in `prototype/ledger.py` (v0.3).

Answers Design Memo 01 §9's open question: *"manual tiers vs. learned."*

## Decision

**Both, layered.** Manual tiers (Design Memo 02) remain the prior; an offline learning pass adjusts from track record:

- `learn_entrenchment(min_outcomes=3)`: for claims with ≥3 recorded outcomes, `entrenchment = 1 − Brier`, where each outcome is scored against the claim version **live at the outcome's time** (bitemporal lookup, not the current score). Claims without enough outcomes keep their manual tier — *no data, no learning*.
- Learned changes are ordinary `entrenchment_set` events with `learned: true`, actor `system`. Fully auditable; a human can see exactly which outcomes moved the tier.
- The pass is **manual/offline** (like Letta's sleep-time consolidation), not automatic on every outcome — entrenchment should move on evidence batches, not jitter per event.

## Why Brier → entrenchment is the right map

Entrenchment answers "how hard should this belief be to dislodge." A claim whose credences predicted outcomes well (low Brier) has *earned* resistance to revision; one that was confidently wrong has not. `1 − Brier ∈ [0,1]` is the direct calibration-to-entrenchment map, no extra parameters.

## Schema note (bug fixed along the way)

`outcomes` was `PRIMARY KEY(claim_id)` — multiple outcomes per claim silently clobbered each other, which made learning impossible. Now `PRIMARY KEY(claim_id, t)`; `record_outcome` appends. `kill_metrics` Brier now also uses score-at-outcome-time for consistency.

## Open (not decided here)

- Stability-based learning for claims that never resolve (churn → entrenchment decay). Needs its own validation; not in v0.3.
- Blending weights between manual prior and learned value (currently full replacement when data suffices).
