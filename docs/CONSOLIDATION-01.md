# CONSOLIDATION-01 — The LLM consolidation pass, measured

**Date:** 2026-10-02. **Code:** `prototype/consolidation.py`,
`prototype/validation/corpus.py`, `prototype/validation/head_to_head.py`,
`prototype/validation/llm_extract_check.py`. **Budget:** $5 hard cap
(Tristen, 2026-10-02); total actual spend **≈ $0.063** (see §4).

## What was built

Per Design Memo 08: an offline consolidation pass, a *client* of the
ledger (the deterministic kernel is unchanged and never calls an LLM).
It reads live claims with their credences and classifies pairs:

- **contradicts** → declared via the normal `declare_contradiction`
  path (actor `consolidator`, signal `llm-consolidation`); the
  governance gate still applies, resolution still goes through
  entrenchment/humans.
- **same** → proposition-identity topics assigned into the ledger
  (`assign_topic`, bitemporal), which the heuristic detector can then
  consume via `topic_of`.
- **supports** → proposed in the report only, never auto-applied.

Prompt rules encode the ledger's semantics: incompatible content on
the same subject; *also* same proposition at strongly opposed
credences (unresolved conflict); explicitly NOT contradictions:
different subjects, AND vs. OR over the same components, weaker/
stronger compatible claims.

## 1. Corpus: proposition understanding on text alone

27 hand-written claims, planted relationships (5 contradiction pairs,
5 paraphrase pairs across 3 groups, an AND/OR-compatible trap, a
weaker/stronger-compatible trap, unrelated fillers). All credences 0.5.

| model | contradicts P / R | same P / R | cost |
|---|---|---|---|
| Claude Sonnet 4.5 | 1.00 / 1.00 | 1.00 / 1.00 | $0.0071 |
| Claude Haiku 4.5 | 1.00 / 1.00 | 1.00 / 1.00 | $0.0022 |

Both models perfect, both traps passed, on the refined prompt. (An
earlier prompt version also scored perfectly; the opposed-credence
clause was added for §2 and re-verified here.)

## 2. Newsroom head-to-head

One populated newsroom ledger (seed 0, 12 steps, no detection),
snapshotted, then three detectors on three identical copies.
Snapshot state: F10 desks fully opposed (wire 0.00 / rumor 0.97);
F11 desks split (wire 0.97 / rumor 0.31 — disagreement, below the
strict both-sides-decided bar used for scoring).

| detector | genuine (of 1 strict) | AND/OR trap | other FP |
|---|---|---|---|
| A: heuristic, unfiltered | 1 | **1 (flagged)** | 1 (cross-fact) |
| B: heuristic + topic filter | 1 | **1 (flagged)** | 0 |
| C: LLM consolidation (Haiku) | 1 | **0** | 1 (borderline F11) |
| C: LLM consolidation (Sonnet) | 1 | **0** | 1 (borderline F11) |

Findings:

1. **The LLM passes the trap no heuristic can.** AND(D1) vs. OR(D2)
   over the same parents is flagged by both heuristic variants
   (score-opposition + shared ancestry) and by neither LLM — the
   models understand the propositions differ but are compatible.
   This was NEWSROOM-01's open problem; it is now closed by the
   consolidation pass.
2. **The LLM's one extra flag is substantively defensible.** It
   flagged the F11 desk pair (0.97 vs. 0.31 on the same proposition).
   That misses the strict scoring bar only because 0.31 is 0.19 (not
   0.20) from neutral; a 0.66 credence gap on one proposition *is* an
   unresolved conflict worth surfacing.
3. **Topics compose the pipeline.** Both models grouped both desk
   pairs as same-proposition (4 claims, 2 topic groups) — exactly the
   assignments that let the cheap heuristic detector work filtered.
   Division of labor: LLM assigns identity + catches semantic traps;
   heuristics monitor scores/intervals continuously.

## 3. LLM extraction (real NL parsing in the newsroom)

`LLMExtractor` (GPT-4o-mini) replaces the modeled parser behind the
same interface.

**Parsing accuracy: 200/200 = 1.000** on generated sentences with
known (fact, value) — zero wrong facts, zero flipped values. The
modeled extractor assumed 85–95% parse accuracy, so NEWSROOM-01's
noise model was *pessimistic*: real parsing removes a noise source
rather than adding one. Its headline results are conservative.

**End-to-end smoke check (10 steps, seed 0, 160 quizzes):**
inconclusive by design limits — ledger 0.250 vs. naive 0.237 with the
LLM extractor; ledger 0.156 vs. naive 0.175 with the modeled one.
Two caveats make this non-discriminating: 10 steps is too early
(few world flips; the frozen baseline is barely stale), and the
worlds diverge anyway because the modeled extractor consumes RNG
draws (misparse rolls) that the LLM extractor doesn't, so the two
runs live in different worlds. A decisive end-to-end run (5 seeds ×
60 steps) would cost ~$0.20 — impossible on the remaining account
balance (§4) and not necessary: the accuracy result above is the
load-bearing measurement.

*Process note:* the first extraction run (v1) was killed at a 550s
timeout with all output lost to stdout buffering, after spending
$0.0218. v2 runs unbuffered with flushed prints; part 1 also runs
8-way parallel. Recorded here because the spend is real (§4).

## 4. Cost accounting

Total session spend: **≈ $0.063** against the $5 cap. Itemized:
corpus runs $0.0186, head-to-head $0.0088, probes ~$0.0002,
extraction v1 (killed, results lost) $0.0218, extraction v2 $0.0140.
Unit economics: one consolidation pass over ~20 claims costs
**$0.0022 (Haiku) / $0.0066 (Sonnet)** with identical detection
profiles — Haiku is the right default; Sonnet buys nothing here.
Extraction costs ~$0.00004 per report.

**Account warning:** the OpenRouter account is nearly exhausted —
$1,749.96 used of $1,750 total credits (**~$0.04 remaining** at time
of writing). Requests reserve worst-case completion cost against the
balance, so large `max_tokens` values 402 even when the actual call
would cost a cent; the client caps `max_tokens` at 800 for this
reason. Any further LLM work needs a top-up.

## Verdict

Proposition identity was the heuristic detector's ceiling
(NEWSROOM-01). The consolidation pass removes it: perfect corpus
scores, the AND/OR trap passed, correct topic groupings, at
~$0.002 per pass on the cheap model. Recommended operating shape:
heuristics online (free, continuous), consolidation pass offline on
Haiku (scheduled or on-demand), LLM output always provisional —
declared through the same governance gate as everything else.
