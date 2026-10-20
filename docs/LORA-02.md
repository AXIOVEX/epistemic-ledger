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


## Results - MEASURED 2026-10-20 (verdict: KILLED)

### Grid and selection

All four cells trained cleanly on the RTX 5060 Ti, which was shared
all day with another workload's 27B model server (a 6-step smoke test
verified training fit in the free memory before the grid launched).
Train times and final losses: lr5e5-ep2 1085 s / 0.004425;
lr5e5-ep3 1611 s / 0.002956; lr1e4-ep2 1070 s / 0.004428;
lr1e4-ep3 1599 s / 0.003229.

Dev census (144 published-style sentences per cell): the unadapted
base scored balanced accuracy 0.9375 (assert 0.875, deny 1.000) -
the published-style dev did discriminate at base level, where
LORA-01's dev had nearly saturated. All four adapters scored a
perfect 1.000 with zero abstentions, so discrimination among the
adapters was nil and the frozen tie-break (lower learning rate,
then fewer epochs) selected lr5e5-ep2, the gentlest configuration.
Winner adapter sha256 7d375a5530f1e3df5e309858703506961b28c22ca601e52616f22925765f930d;
merged Q4_K_M GGUF 5,780,090,496 bytes, sha256
95ef93ad8aff28bc72274e11de6e0809127edd349f45343a9953b43aff5a8807.

### One-shot census

Accuracy (assert / deny), abstentions, parse errors. L0 = unadapted
production model; L1 = winner, merged GGUF form.

| corpus | L0 | L1 |
|---|---|---|
| held-out (sealed) | 0.979 (0.958 / 1.000), abst 0, err 0 | 0.965 (1.000 / 0.931), abst 4, err 0 |
| REALWIRE | 0.840 (0.831 / 0.847), abst 0, err 2 | 0.679 (0.729 / 0.639), abst 39, err 0 |
| REALWIRE-T | 0.929 (0.958 / 0.891), abst 0, err 2 | 0.827 (0.958 / 0.655), abst 19, err 0 |
| INDIE | 0.993 (1.000 / 0.986), abst 0, err 0 | 0.986 (0.986 / 0.986), abst 2, err 0 |
| FREETEXT | 1.000 (1.000 / 1.000), abst 0, err 0 | 1.000 (1.000 / 1.000), abst 0, err 0 |

### The frozen bars, judged

Primary (held-out): assert 1.000 (bar 0.90) PASS; deny 0.931 (bar
0.90) PASS; gap 0.069 (bar 0.10) PASS; abstentions 2.8% (bar 3%)
PASS; error reduction at least 50% per pool: assert errors 3 to 0
PASS, deny errors 0 to 5 FAIL - the frozen rule says a pool where
the base makes zero errors must stay at zero. PRIMARY FAILS.

Confirmatory: REALWIRE assert 0.729 (bar 0.90) FAIL; deny 0.639
(bar 0.86) FAIL; abstentions 29.8% (bar 3%) FAIL. REALWIRE-T total
fell 0.102 against L0 (allowance 0.02) FAIL; its deny fell 0.236
(allowance 0.05) FAIL. CONFIRMATORY FAILS.

Guards: INDIE 0.986 (bar 0.97) PASS; FREETEXT 1.000 (bar 0.95)
PASS; parse errors 0 PASS; abstentions at most 3% on every corpus
FAIL (REALWIRE 29.8%, REALWIRE-T 15.0%).

### Verdict: KILLED

The downstream newsroom run was not run; it was gated on primary,
confirmatory, and guards all passing. No second grid, no retuning.
The production default remains the unadapted Qwen3.5-9B (Q35A).

### What the measurement says

- On sealed authored sentences this adapter is the strongest local
  stance extractor the program has measured: it fixed every assert
  error the base model made (0.958 to 1.000) and held deny at 0.931.
- On real published copy the same adapter falls apart. It abstains
  on 30% of REALWIRE (39 of 131) - worse than LORA-01's adapter
  (14 of 131), at a gentler learning rate, with training data
  designed specifically to prevent exactly this. REALWIRE accuracy
  fell from 0.840 to 0.679, and REALWIRE-T deny accuracy fell from
  0.891 to 0.655.
- Two studies with two different distractor designs now show the
  same failure shape, so the binding constraint is not the
  distractor mix. It is the gap between authored training sentences
  and real published sentences: training on authored copy teaches
  list-checking in a style real sentences do not present cleanly,
  and "not in the list" becomes the answer whenever a real sentence
  is messy.
- Consequence: the LoRA line closes here. A successor would need
  stance-labeled real published sentences as training data - a
  different data program, not another round of authored data - and
  would need its own design and authorization.

### Execution record

- Data sealed before training (c264f7b); runners committed before
  the grid (5441901). Grid ran 2026-10-20 09:28-11:00 EDT; dev
  census about 11:21-11:52 (slower than LORA-01's under GPU
  sharing; results unaffected); merge about 11:54; censuses ran
  12:05-12:45 EDT (walls: L0 310.6 s, L1 405.1 s).
- Serving: llama.cpp b11081 on port 8084, config N (context 8192,
  parallel 4), alias qwen3-8b-local. Each server's identity was
  verified from /v1/models before its census (production:
  8,953,803,264 parameters / 5,669,554,176 bytes; merged:
  9,197,093,888 / 5,769,121,792). Both servers were shut down after
  their runs; the final shutdown was verified by process absence
  and port closure.
- Incidents: (1) The VM's intermittent shell write restriction
  recurred mid-day; desktop work ran through the desktop-relay
  GitHub-API failsafe (channel lora) with no loss of work.
  (2) The GPU was shared all day with another workstream's 27B
  llama-server, which was never disturbed. (3) The server launcher
  scripts echoed process IDs one indirection off the real
  llama-server PIDs; shutdowns were re-verified against the actual
  process and the port.
- Artifacts banked in e2be9c2: lora02_dev_results.json (sha256
  6fbf8fa9dcea8244742f1b0f459f31425ad9db5526f8f68a642af5fc19176145),
  lora02_census_L0.json (8582c3f570ec150b63d9347530189b15cc0618469fa33f3adfaeb1b41425bfd6),
  lora02_census_L1.json (75c5b01e0a7520570c12304a22a272f40fd1108cfcf5c829fd404b647eafd6b5).
  Adapters and the merged GGUF remain on the desktop under ~/lora02/.
