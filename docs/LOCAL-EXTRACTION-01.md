# LOCAL-EXTRACTION-01 — Decisive end-to-end validation with a free local model

**Date:** 2026-10-02. **Status:** complete. Results:
`prototype/validation/llm_extract_local_results.json` (commit
`4e85a45`, md5 `11eee7bef385c4b2591cb6f674bf876c`).

## Why this run exists

CONSOLIDATION-01 left one decisive measurement unmade: the end-to-end
newsroom trial with *real* LLM extraction at decisive scale (5 seeds ×
60 steps). The OpenRouter version (~$0.20) was blocked on account
balance (~$0.04 remaining of $1,750). This run makes the measurement
at $0 with a local model: **Qwen3-8B Q4_K_M**, llama.cpp server on the
owner's desktop (RTX 5060 Ti; GPU mapping verified live at launch —
GPU 1 memory 176 MiB → 6,027 MiB), via `newsroom.LocalExtractor`
(same prompt and parsing as `LLMExtractor`; thinking disabled; calls
counted; failures raise). 5,120 extraction calls total, zero spend.

The claim measured is deliberately a *different* one from the
OpenRouter run's: not "GPT-4o-mini extracts perfectly" but "a free
local model extracts well enough that the ledger's end-to-end
advantage survives real parsing." Both agents share one extraction
stream per trial, as in NEWSROOM-01.

## Part 1 — parsing accuracy (protocol identical to CONSOLIDATION-01)

200 generated sentences, known (fact, value), seed 7:

| extractor | accuracy | fact wrong | value flipped | calls | wall |
|---|---|---|---|---|---|
| GPT-4o-mini (OpenRouter) | 1.000 | 0 | 0 | 200 | — |
| **Qwen3-8B local** | **1.000** | **0** | **0** | **200** | **32.2 s** |
| Modeled (assumed) | 0.85–0.95 | — | — | — | — |

## Part 2 — end-to-end, decisive form (5 seeds × 60 steps, 4,800 quizzes per condition)

| condition | ledger err | naive err | naive errors eliminated | derived ledger | derived naive | derived eliminated |
|---|---|---|---|---|---|---|
| **Local extraction (Qwen3-8B)** | **0.1506** | **0.1935** | **22.2%** | **0.1108** | **0.2825** | **60.8%** |
| Modeled (re-run, same code) | 0.1452 | 0.1833 | 20.8% | 0.1450 | 0.2975 | 51.3% |

Per-seed (local): the ledger wins **5/5 seeds overall and 5/5 on
derived claims** — including seed 3, the one seed the modeled run
loses (0.152 vs 0.149). Seed 4 is the widest gap (0.147 vs 0.261;
derived 0.108 vs 0.567, where the frozen agent's stale derived claims
collapse). 984 extraction calls per seed, 230–285 s per seed
(~0.26 s/call serial) vs ~21 s for a modeled seed.

## Reading

- **Reproducibility check passed:** the modeled re-run reproduces
  NEWSROOM-01's headline numbers exactly (20.8% overall, 51.3%
  derived) on the same code path.
- **The advantage survives real parsing — and widens where it
  matters.** Real extraction (1.000) is cleaner than the modeled
  0.85–0.95 misparse assumption, and the cleaner stream helps the
  revising agent more than the frozen one on derived claims (60.8%
  vs 51.3% of naive errors eliminated): derived claims are where
  revision compounds, and misparses were taxing exactly that.
- **Honest nuance:** absolute error levels differ slightly across
  conditions (local ledger 0.1506 vs modeled 0.1452) because the
  report streams are matched in distribution, not identical (the
  standing RNG-divergence caveat). The within-condition
  ledger-vs-naive gap is the measured claim; cross-condition absolutes
  are indicative only.
- **Verdict:** the decisive run CONSOLIDATION-01 deferred is made.
  For this workload, a free local 8B model is a full substitute for
  the hosted extractor, and the OpenRouter balance is off the
  critical path for extraction validation. (The consolidation pass's
  model comparisons are a separate question — different prompts,
  untested locally.)
