# Real-domain validation: repo-history dogfood

**Date:** 2026-10-01. **Status:** measured.

The context-cleanup experiments were synthetic. This one replays the
epistemic-ledger repo's own git history — real, non-synthetic, timestamped
change — as the observation stream. Ten factual claims about the codebase
(epsilon default, materiality default, test count, feature existence) have
objective ground truth per commit via `git show`. Five derived judgments
("trigger discipline tuned", "v0.3 complete", ...) are AND-structured and
use the v0.4 noisy-and combos, so this also exercises joint likelihoods on
real data.

## Method

`prototype/validation/repo_history.py`. Six states: the five prototype-era
commits plus the working tree. The agent observes each fact per state with
credence 0.95 and 10% misread noise; the revisit loop propagates to derived
judgments. Naive baseline: facts observed, derived frozen at the first
commit's values. 30 quizzes per seed (5 derived x 6 states), 5 seeds.

## Ground-truth evolution (1 = true)

| state | eps=.005 | mat=.05 | tests>=14 | contra | learn | D-S | ctxexp | stress | biblio | joint |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| v0.1 prototype | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| trigger stress | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| v0.2 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 1 | 0 | 0 |
| v0.3 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| source verify | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| working tree v0.4 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |

## Results

| seed | ledger err | naive err |
|---:|---:|---:|
| 0 | 0.067 | 0.500 |
| 1 | 0.233 | 0.700 |
| 2 | 0.100 | 0.433 |
| 3 | 0.033 | 0.500 |
| 4 | 0.067 | 0.500 |
| **mean** | **0.100** | **0.527** |

**Staleness reduction: 0.427 — the ledger eliminates 81.0% of naive errors
on real repository history.** The naive baseline froze its judgments at v0.1
(everything False) and missed every feature that shipped later; the ledger
tracked them. Residual ledger error (0.100) is the injected 10% misread
noise, not propagation failure.

## What this establishes (and doesn't)

- The revision machinery works on real, messy data: file additions, API
  changes, regex-extracted facts — not just synthetic flips.
- Noisy-and combos compose correctly outside the toy world.
- It does NOT establish performance on natural-language belief revision
  (no retrieval, summarization, or contradiction in this stream). That
  remains the next validation target.
