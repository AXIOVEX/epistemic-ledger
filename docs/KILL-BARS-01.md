# KILL-BARS-01 — The kill bars, calibrated across workloads

**Date:** 2026-10-02. **Status:** complete; two bars adjusted under
a pre-stated rule. Battery: `prototype/validation/
killbar_calibration.py`; results: `killbar_calibration_results.json`.

## Why

The bars were set one workload at a time: trigger and flag bars
from TRIGGER-STRESS-01's single configuration, churn from
CHURN-01, and `max_fanout`, `n_open_contradictions`, and
`override_rate` marked provisional with no data at all. This
battery measured every bar across the program's healthy workload
families: stress config A (300 claims / 40 facts, the
TRIGGER-STRESS-01 shape), stress config B (600 claims / 25 facts,
hub-heavier, fresh), and newsroom modeled trials on seeds 0–9
(0–4 published, 5–9 fresh).

**Adjustment rule, fixed before running:** a bar is adjusted only
if a healthy workload breaches it, then to observed max × 1.25
with the old value recorded. Bars are never tightened on healthy
data — tightening needs failure data.

## Results

| bar | value | observed (healthy) | verdict |
|---|---|---|---|
| trigger_recall ≥ 0.90 | — | 0.960 (A), 0.979 (B) | CONFIRMED |
| trigger_precision ≥ 0.60 | — | 0.715 (A), 0.711 (B) | CONFIRMED |
| mean_flags ≤ 25 | → **37** | 17.1 (A), **29.2 (B)** | ADJUSTED (29.2 × 1.25) |
| max_flags ≤ 60 | → **270** | 52 (A), **215 (B)** | ADJUSTED (215 × 1.25) |
| max_material_churn ≤ 8 | — | newsroom max 8, mean 4.8 | CONFIRMED, TIGHT |
| max_fanout ≤ 100 | — | 76 (stress), 3 (newsroom) | CONFIRMED (was provisional) |
| brier ≤ 0.25 | — | newsroom max 0.2501 | HELD — see below |
| override_rate ≤ 0.20 | — | 0.0 everywhere | UNMEASURED in substance |
| n_open_contradictions ≤ 10 | — | max 1 | CONFIRMED (was provisional) |

## The three judgments worth explaining

**Flag bars (adjusted).** Config B is a healthy workload the
system handles correctly (recall 0.979) — it simply has more
claims per fact, so one hub revision legitimately flags 215
claims. The bars were measuring graph shape, not pathology. They
are adjusted per the rule, and the code now says what they are:
review-burden alarms for a given deployment's graph, not
universal constants. A size-normalized successor metric is the
honest future fix; silently re-scoping the bars mid-battery would
not have been.

**Material churn (confirmed, tight).** One newsroom seed reached
exactly 8 — at the bar, not over it (breach is strictly greater).
CHURN-01's deliberate one-point margin over the then-worst healthy
seed (7) is now fully consumed. The bar stands per the rule, and
this is recorded as the battery's tightest margin: the next
healthy seed at 9 forces the adjustment conversation with data.

**Brier (held, against the mechanical rule).** Seed 2's 0.2501
technically exceeds the 0.25 bar by 0.0001, which under the
pre-stated rule would "adjust" the bar to ~0.31. **Not done.**
The Brier bar is not an empirical calibration — 0.25 is the score
of a constant coin-flip predictor, the definitional line for
"worse than chance." Moving it because a run landed on it would
be goalpost-moving in its purest form, and CALIBRATION-01 already
established what seed 2 is: a hard seed read through a
whole-ledger metric, with fact-claim Brier at 0.062. The rule
governs empirical bars; this one is definitional, and the
deviation from the rule is stated here rather than buried.

**Override rate (unmeasured).** Every automated workload records
0.0 — the phenomenon the bar guards (humans overriding the loop
often enough to signal distrust) does not occur in any workload
the program has. The bar stays provisional at 0.20, now honestly
labeled zero-coverage: it will mean something the first time a
human is in the loop, and not before.
