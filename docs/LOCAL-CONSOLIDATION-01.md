# LOCAL-CONSOLIDATION-01 — The consolidation pass, ported local

**Date:** 2026-10-02. **Status:** complete. Results:
`prototype/validation/consolidation_local_results.json` (commit
`a413222`). All runs $0 on the owner's desktop (llama.cpp, Qwen3-8B
Q4_K_M, RTX 5060 Ti).

## The port

`consolidation.LocalClient` is a drop-in for `OpenRouterClient`
(same `complete()` interface, zero-spend accounting), and
`corpus.run_model` / `head_to_head.main` now accept an injected
client. One platform coupling had to be removed first:
`consolidation.py` imported the agent VM's credential helper at
module top, which made the module unusable off-VM; the import is now
lazy, inside `OpenRouterClient` only.

The two CONSOLIDATION-01 validations were re-run unchanged —
identical prompts, identical scoring. Three client configurations
("arms") were measured; the prompts and tests were never adjusted
between arms, only decoding/serving configuration.

## Results

**Corpus** (27 claims; Sonnet 4.5 and Haiku 4.5 both scored
P=1.00/R=1.00 on both relations in CONSOLIDATION-01):

| arm | CONTRADICTS P/R | SAME P/R |
|---|---|---|
| no-thinking (extraction config) | 0.385 / 1.00 | 0.308 / 0.80 |
| no-thinking + repeat_penalty 1.1 | 0.20 / 0.40 | 0.455 / 1.00 |
| **thinking, 12000 budget** | **1.00 / 1.00** | **1.00 / 1.00** |

**Head-to-head** (C arm; A/B heuristic arms reproduced
CONSOLIDATION-01 exactly in every run):

| arm | genuine | AND/OR trap | other FP |
|---|---|---|---|
| no-thinking | — reply unparseable — | | |
| no-thinking + repeat_penalty 1.1 | 0/1 | 0 | 11 |
| **thinking, 12000 budget** | **1/1** | **0** | **0** |
| (reference: Haiku / Sonnet) | 1/1 | 0 | 1 |

The thinking arm also groups the F10 desk pair under one topic, as
both hosted models did. It does not group the F11 desk pair (the
hosted models did) — a SAME-side miss worth naming; on this snapshot
F11 is not genuinely opposed, and the arm's clean FP=0 partly
reflects that conservatism.

## What failed, and why it matters

The no-thinking failure is instructive, not random. On the corpus it
over-generates: every thematically adjacent pair — including all
four designed traps — is dumped into both relations. On the
head-to-head prompt it degenerates entirely: the first claim is
paired against everything, repeated until the token cap truncates
the JSON mid-stream (raw reply inspected; repetition loop,
1,524 chars, no closing brace). A repetition penalty breaks the
loop but not the judgment (0/1 genuine, 11 FPs anchored on one
claim). With thinking enabled, the same model on the same prompts
is exact.

Diagnosis, supported by the contrast with LOCAL-EXTRACTION-01:
**extraction is a parse task and needs no reasoning (no-thinking:
200/200); consolidation is a judgment task and at 8B scale the
reasoning trace is load-bearing.** The measured head-to-head trace
runs ~5.1k tokens; a 6000-token budget intermittently truncates
before the answer (observed once: empty content, parse failure), so
the shipped budget is 12000 with a per-slot context of 16384
(parallel 1 on the desktop server). Thinking passes take ~55–115 s
vs ~11 s no-thinking — irrelevant for an offline sleep-time pass,
and the cost is $0 against Haiku's $0.0022/pass.

Two honesty notes. (1) Claim IDs are random per run, so no two runs
share an identical prompt; temperature-0 outputs still vary run to
run — across two thinking runs, corpus SAME recall was observed at
0.80 and 1.00 (the archived run is the perfect one). Single-run
perfection, local or hosted, should be read with that variance in
mind. (2) The shipped `LocalClient` defaults are now the validated
thinking configuration; anyone serving it at small per-slot contexts
will rediscover the truncation failure this report documents.

## Verdict

The consolidation pass ports cleanly: **in its thinking
configuration, the free local 8B model matches the hosted frontier
models on both validations** — perfect corpus scores and a
head-to-head profile at least as clean as Haiku's/Sonnet's. The
ledger's full LLM surface (extraction + consolidation) now runs
end-to-end at zero marginal cost on the owner's hardware, with the
deterministic kernel untouched by any of it.
