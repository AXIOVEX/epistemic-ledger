# LORA-02 — stance-fidelity adapter, second study (headroom-based bars, near-miss distractors)

**Status: DESIGN FROZEN 2026-10-20. Execution authorized by Tristen
on 2026-10-20 ("do it now please", directing the successor study
proposed in the LORA-01 close-out).** This document freezes the
protocol before any LORA-02 data is built or any training runs.
LORA-01's discipline carries over unchanged: topic-disjoint
partitions, a sealed held-out corpus whose hash is committed before
training, exactly one selected configuration ever measured on
held-out or REALWIRE-family corpora, one-shot measurement, and
predeclared kill criteria reported with the same prominence as a
pass.

## Question

LORA-01 (measured 2026-10-20, verdict KILLED) established that the
base model's residual stance errors are substantially learnable:
its adapter removed 5 of the base model's 7 assertion errors on a
sealed held-out set and nearly eliminated the assert/deny gap
there. It failed as a production candidate for two measured
reasons:

1. Its primary bar demanded an absolute +0.10 assertion-accuracy
   gain, which was unreachable once the same-session baseline
   measured 0.903 (maximum possible gain 0.097).
2. On real published copy it learned to abstain — answering "no
   listed fact" for sentences that do match one (14/131 REALWIRE,
   11/127 REALWIRE-T, where the baseline abstains on none) — and
   REALWIRE-T total accuracy regressed 0.929 → 0.882.

**LORA-H2:** an adapter trained with the same truth-orthogonal
stance data, but with (a) distractors redesigned as near-misses
that teach "commit unless no listed fact truly matches" instead of
blanket abstention, and (b) a gentler grid point available, keeps
LORA-01's stance gains on the baseline protocol without
transferring abstention to real published copy.

## What changes vs LORA-01, and what does not

Unchanged: the trained behavior (baseline Arm A / Q35A extraction,
single call, production prompt shape); the base model
(`Qwen/Qwen3.5-9B`); the QLoRA method (NF4 double-quant base, rank
16, alpha 32, dropout 0.05, language-model layers only, cosine
schedule, warmup ratio 0.03, effective batch 32, max seq 1024,
BF16 compute, gradient checkpointing, paged 8-bit AdamW,
completion-only loss); the census protocol and corpora; the
downstream protocol and its gate; the kill discipline.

Changed, each tied to a LORA-01 measurement:

- **Improvement bar form.** The primary improvement clause is now
  an *error-reduction* requirement (below): the adapter must
  remove at least half of the baseline's errors in each pool.
  This expresses the same intent as LORA-01's +0.10 clause
  relative to the headroom the baseline actually leaves, instead
  of against a headroom the design guessed at.
- **Abstention is a first-class bar.** LORA-01 counted census
  abstentions but barred them only downstream. LORA-02 bars them
  on every census corpus (≤ 3%): an adapter that buys accuracy
  with silence fails, whatever its accuracy.
- **Distractor design and rate.** LORA-01: 80/872 ≈ 9% easy
  distractors (off-topic sentences → fact −1). LORA-02: ≈ 5%
  distractors, the majority *near-miss* — sentences topically
  adjacent to the block's facts (same subject family, different
  claim; or a claim about a pool proposition that is not in this
  block), which are only answerable by checking content against
  the listed facts. The −1 label must be earned by a true
  no-match, not triggered by unfamiliar texture.
- **Training pool grows.** LORA-01's dev and held-out propositions
  (24 topics, 288 rendered sentences) are unsealed by its
  completion and join LORA-02's training data. Twelve new
  propositions are authored for training. Dev and held-out for
  LORA-02 are entirely new propositions.
- **Dev is published-style.** LORA-01's dev saturated (baseline
  0.993; three adapters at 1.000), so selection carried little
  information. LORA-02's dev renderings are written as published
  copy — attribution, hedging, layered negation — in the texture
  where the baseline actually errs. The selection metric and
  tie-break are unchanged.
- **Grid.** Learning rate {5e-5, 1e-4} × epochs {2, 3}. LORA-01's
  winner was its gentlest cell; 5e-5 tests whether less fitting
  preserves real-copy commitment. Seed 20261020.
- **Serving form.** The merged Q4_K_M GGUF is the primary serving
  form, stated upfront: LORA-01 proved the adapter-GGUF form
  unattainable for this architecture (llama.cpp's converter
  raises NotImplementedError on the fused linear-attention
  tensors, for adapters from both trainer implementations). The
  measured artifact is the winner merged into the base weights
  and quantized to Q4_K_M, served standalone, config N, thinking
  disabled, exactly as LORA-01's fallback was measured.

## Data (frozen discipline)

Topic-level disjointness governs, as in LORA-01: no proposition in
any LORA-02 partition may duplicate, paraphrase, or sit adjacent
to any of the 24 REALWIRE / REALWIRE-T propositions, and no
proposition appears in more than one LORA-02 partition.

- **Train (~1,270 examples).** (a) All of LORA-01's training
  sources: INDIE 144 + FREETEXT 144 + COUNTERFACTUAL T1–T3 72 +
  LORA-01's 36 authored propositions 432 = 792. (b) LORA-01's dev
  + held-out corpora as training corpora: 288. (c) Twelve newly
  authored propositions (6 false / 6 true) × 12 renderings in
  published style: 144. (d) Distractors ≈ 5%: near-miss sentences
  (authored against the training proposition pool) plus a minority
  of easy off-topic distractors. Assert/deny balance stays 50/50
  across non-distractor examples; stance labels remain orthogonal
  to real-world truth by construction. Blocks are 12-proposition
  facts blocks with the target at a uniform random position, as in
  LORA-01.
- **Dev (12 new propositions, ~144 sentences).** Published-style
  renderings. Used only for grid selection.
- **Held-out (12 new propositions, ~144 sentences, sealed).**
  Famous-leaning, 6 false / 6 true, ≈6 assert + ≈6 deny published-
  style sentences per proposition, gold by construction. The
  corpus file's SHA-256 is committed before training starts; its
  sentences are never used for selection, tuning, or prompting.

**Contamination screens (run and reported before training):**
token-Jaccard overlap of every train/dev/held-out sentence against
every REALWIRE/REALWIRE-T sentence ≤ 0.80, as in LORA-01; the
topic-exclusion checklist is signed off in the execution record.

## Configuration selection (the only tuning permitted)

Grid (predeclared, 4 cells): learning rate {5e-5, 1e-4} × epochs
{2, 3}. All other hyperparameters as frozen above. Selection
metric: dev balanced accuracy = mean(assert-pool acc, deny-pool
acc); ties break to the lower learning rate, then fewer epochs.
**Exactly one** selected configuration is ever evaluated on
held-out or REALWIRE-family corpora. There is no second campaign:
if the selected adapter fails the bars, LORA-02 records KILLED
and stops (a successor study needs a new design and new
authorization).

## Arms and measurement (frozen census + downstream protocol)

- **L0:** Q35A baseline (production Q4_K_M GGUF), re-measured in
  the same session (cross-session baseline reuse is not permitted
  for the primary comparison).
- **L1:** the dev-selected adapter, merged and served as
  specified above.
- Census cells (Arm A protocol): held-out (primary), REALWIRE,
  REALWIRE-T, INDIE + FREETEXT (regression guards). One run per
  (model, corpus); no retries, no reseeding.
- Downstream (REALWIRE newsroom seeds 0–4 × 60 steps) runs
  **only if** the primary bar, the confirmatory bar, and every
  regression guard pass.

## Success bars and kill criteria (frozen)

- **Primary (held-out census):** assert ≥ 0.90 AND deny ≥ 0.90
  AND |gap| ≤ 0.10 AND error reduction ≥ 50% in each pool (L1
  errors ≤ half of L0's errors per pool; if L0 makes zero errors
  in a pool, L1 must also make zero) AND abstentions ≤ 3%.
- **Confirmatory (REALWIRE census):** assert ≥ 0.90 AND deny
  ≥ 0.86 AND |gap| ≤ 0.10 AND abstentions ≤ 3%. REALWIRE-T:
  total accuracy within 0.02 of L0 AND deny accuracy within 0.05
  of L0 (no-regression).
- **Regression guards:** INDIE total ≥ 0.97; FREETEXT ≥ 0.95;
  parse-failure rate ≤ 1% on every cell; abstentions ≤ 3% on
  every census corpus.
- **Downstream success:** aggregate ledger error ≤ 0.28 (vs Q35A
  0.3194), supportive evidence; the census bars are decisive.
- **Kill:** any primary, confirmatory, or guard clause fails →
  adapter KILLED as a production candidate, reported with the
  same prominence as a pass. No retuning against held-out signal,
  no reseeding, no second grid.

## Execution record requirements

Runner hash, data-builder hash, train/dev corpus hashes, sealed
held-out hash (pre-training), adapter hash, merged-GGUF hash,
training wall time, peak VRAM, dev-grid results for all 4 cells,
and every deviation or incident — banked in this repository
alongside the results JSONs, following the STANCE-02 record
standard. Invalid runs (infrastructure failure) are quarantined
and disclosed, never averaged in.

## Estimated cost

Data build ~1 h (authoring dominates); grid training 4 × ~20–35
min on the 5060 Ti (training pool ≈ 1.6× LORA-01's); censuses
~20 min; downstream (if gated in) ~40 min. $0 API spend.

## Authorization

Design frozen 2026-10-20 by the agent under Tristen's direction
("do it now please", 2026-10-20, directing the successor study
proposed in the LORA-01 close-out). Execution — data build, grid
training, and the one-shot measurement — is authorized by the
same directive.
