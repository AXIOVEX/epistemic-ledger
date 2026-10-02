# OVERRIDE-CAL-01 — The last unmeasured kill bar, measured

**Question.** KILL-BARS-01 calibrated every bar except one:
`override_rate` (humans hand-set > 20% of score revisions = the
loop is untrusted) sat at 0.0 in every workload because nothing
automated ever calls `manual_score`. A bar nothing can trip is not
a bar. This run puts a reviewer in the loop.

**Instrument.** `prototype/validation/override_calibration.py`.
`run_trial` gained an optional `reviewer` hook (default None;
baseline reproduction verified exact before any persona was read).
A reviewer is a **scripted simulation of a human editor** — stated
cadence, deviation threshold, reliability, and (for one persona)
error rate — correcting fact and desk claims whose scores deviate
from ground truth past its threshold, via the real human path,
`manual_score`. Personas are not humans; every conclusion below is
about the instrument's response curve, and the bar's human
calibration remains outstanding. That limitation is the finding's
frame, not a footnote.

## Results (5 modeled seeds each; baseline ledger 0.1452 / derived 0.1450)

| persona | ledger err | derived err | override_rate | manual/trial |
|---|---|---|---|---|
| spot (10-step, worst only) | 0.1208 | 0.1125 | 0.0047 | 5.6 |
| diligent, 15-step | 0.1225 | 0.1292 | 0.0096 | 11.6 |
| diligent, 5-step | **0.0758** | **0.0858** | 0.0200 | 24.0 |
| noisy (20% wrong-way) | 0.0773 | 0.0858 | 0.0220 | 26.6 |
| diligent, every step | 0.0060 | 0.0058 | 0.0351 | 42.6 |

No persona breached any kill bar on any seed.

**The bar's shape, now known.** Even a reviewer who corrects
*every* deviating claim *every* step produces override_rate 0.035 —
a sixth of the bar — because the denominator (all score revisions)
grows with the ledger's own activity. In an active ledger the bar
is structurally near-untrippable; it can only bite in a *quiet*
ledger, where a handful of hand edits dominates a small revision
count. That is precisely the condition the bar exists to catch —
a store humans are driving by hand because the loop isn't trusted.
**Verdict: 0.20 CONFIRMED, reclassified from unmeasured to
calibrated-against-scripted-reviewers**, with the denominator
effect recorded in the KILL_BARS comment.

**Overrides help, and the loop absorbs bad ones.** A diligent
5-step reviewer cuts ledger error from 0.1452 to 0.0758. The noisy
reviewer — one correction in five deliberately wrong-way — lands
at 0.0773, statistically indistinguishable from diligent: wrong
overrides are re-corrected by subsequent evidence instead of
amplifying. The human path is a net asset at every cadence tested.

## Two defects found by the harness, both fixed (v0.11.1)

1. **`kill_metrics` crashed on first human use.** Churn history
   was sorted on the caller-supplied `t`, which mixes types (ISO
   strings from the wall clock, ints from logical clocks) — the
   first `manual_score` inside a step-clocked trial raised
   `TypeError`. Fixed by ordering on log sequence (append order is
   transaction order); regression test added.
2. **`manual_score` did not propagate.** A human correction set
   the claim's score but never revisited dependents, leaving
   derived claims stale until evidence next touched the parent —
   contradicting the ledger's core contract. Measured A/B
   (pre-fix): identical diligent reviewer, derived error 0.1075
   as-built vs 0.0858 with propagation. Fixed: `manual_score` now
   runs the revisit pass like every other score change. Post-fix,
   the plain diligent persona reproduces the propagation arm's
   numbers **exactly** (0.0758 / 0.0858), and the suite gained a
   propagation test. One existing test's trigger-log count moved
   1 → 2 (the override's revisit pass is now audited, as it
   should be).

**Sharp edge, documented not changed:** two versions of one claim
at the same `t` violate the `(claim_id, txn_from)` primary key, so
logical-clock callers must tick per version. The wall-clock
default makes this a non-issue in practice; changing the store's
keying for it is not warranted by anything measured here.
