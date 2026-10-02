# Design Memo 07 — v0.6 follow-through bundle

**Date:** 2026-10-01. **Status:** decided; implemented.

Five deferred items from earlier memos, closed in one pass. Each is small;
each had a recorded reason to wait.

## 1. Stability-based entrenchment decay (from Memo 03)

For claims with ≥ 5 revisions but too few outcomes for Brier learning,
`learn_entrenchment` now decays: `new = old · (1 − min(0.5, flips/n))`
where flips counts crossings of 0.5 between consecutive versions.
Decay only — stability never raises entrenchment. Event basis
`"stability"`, alongside the existing `"brier"` basis. The validation is
the unit test: a 6-flip claim at 0.75 decays to 0.375; a steady claim is
untouched.

## 2. D–S beyond the binary frame (from Memo 04)

`dempster_combine(m1, m2)` implements Dempster's rule over general mass
functions (dicts of frozenset → mass). Binary intervals are the
`{'T','F'}` special case via `interval_to_mass`; `combine_interval` is
reimplemented on the general rule with identical behavior (same K,
same 0.99 refusal). `_interval_conflict` (used by auto-detection)
delegates to it — one code path. Total conflict (K = 1) raises
ValueError instead of producing nonsense.

## 3. Abstention policy placement (from Memo 04)

**Decision: caller-owned.** The ledger exposes credences and ignorance;
only the caller knows the cost of acting vs. abstaining, and policies
differ by deployment. Baking a threshold into the kernel would force
every caller to fight it. `prototype/policies.py` ships two reference
implementations (`ignorance_gated_policy`, `credence_band_policy`) with
the rationale documented.

## 4. Likelihood elicitation (from Memo 01 §9)

`prototype/elicit.py`: the two-question procedure (Q1: evidence true →
claim?; Q2: evidence false → claim? — the base-rate question people
forget), a 7-point verbal anchor scale, and `elicit_pair()` with a
counter-evidence warning when p_given < p_given_not. Anchors are
conventional, not psychometric claims.

## 5. Kill-criterion bars (from Memo 01 §8)

`KILL_BARS` replaces "bars are guesses": trigger_recall 0.90 /
precision 0.60 / mean_flags 25 / max_flags 60 are calibrated on
TRIGGER-STRESS-01 (measured 0.96 / 0.715 / 17.1 / max 52); brier 0.25
(worse than chance = dead) and override_rate 0.20 are principled;
max_churn 4, max_fanout 100, n_open_contradictions 10 are provisional
tripwires, marked as such. `check_kill_bars()` evaluates the live
ledger; metrics with no data yet (brier before any outcomes) are
skipped, not assumed. Re-tune on real workloads.
