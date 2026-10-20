# LORA-01 — stance-fidelity adapter for the production extraction path

**Status: EXECUTED 2026-10-20 — verdict KILLED (the frozen primary
bar failed; see the Results section at the end of this document).**
Design frozen 2026-10-09; training authorized by Tristen on
2026-10-09; the frozen protocol below was executed as written, and
the production default (Q35A) is unchanged.

## Question

The proof package (STANCE-02, post-freeze addendum 2026-10-09)
established the production default: Qwen3.5-9B with the baseline
extraction prompt (Q35A), downstream ledger error 0.3194. Its residual
defect is known and specific: on published copy asserting famous
falsehoods (REALWIRE), the baseline census reads assert-pool accuracy
0.797 / deny-pool 0.861 — prior interference is reduced by the base
model, not eliminated. The structured protocols fix the bias only by
abstaining (45–48% downstream). 

**LORA-H1:** a LoRA adapter trained on stance-labeled authored data —
with stance labels *orthogonal to real-world truth by construction* —
reduces the residual prior interference on the baseline protocol
itself, without the structured arms' abstention cost.

## Gate review (STANCE-02 LoRA gate, frozen 2026-10-04)

1. *Hosted control demonstrates the skill is achievable* — **MET**
   (Arm EA: REALWIRE 0.977, all frozen bars).
2. *Local structured methods still materially underperform* — **MET on
   raw fidelity** (best local raw census line is Q35A itself; the
   structured family wins only on conditional accuracy), **not met on
   conditional fidelity** — recorded as in the STANCE-02 report.
3. *The gap looks learnable, not architectural* — **PARTIALLY
   supported**: the familiarity gradient (sink analysis) is a
   dose-response in the weights' priors, the classic LoRA-addressable
   shape. Sink 2 (commitment strictness) is a task definition, not a
   deficit, and is **out of scope** for this study: LORA-01 trains the
   baseline protocol, whose failure mode is sink-free prior
   interference.

## What is trained, and what is deliberately not

- **Trained:** the baseline (Arm A / Q35A) extraction behavior —
  single call, production prompt shape, output
  `{"fact": <index>, "says_true": <bool>}`.
- **Not trained:** the structured protocol (its deficit is coverage
  by design, not weight error); consolidation (a judgment task where
  the local model already matches frontier — LOCAL-CONSOLIDATION-01);
  any ledger code (the kernel never learns; adapters live at the
  extraction edge only).

## Base model and serving form (frozen)

- Base: `Qwen/Qwen3.5-9B` (BF16 originals of the production GGUF).
- Method: QLoRA — NF4 double-quantized base, LoRA rank 16, alpha 32,
  dropout 0.05, target modules = all linear projections (attention +
  MLP), cosine schedule, warmup ratio 0.03, effective batch 32
  (8 × grad-accum 4), max sequence 1024, seed 20261009, BF16 compute,
  gradient checkpointing. Hardware: desktop RTX 5060 Ti (16 GB).
- **Serving form (the measured artifact):** the adapter converted to
  GGUF (`convert_lora_to_gguf.py`) and served via
  `llama-server --lora` on top of the **unchanged production
  Q4_K_M GGUF**, config N, thinking disabled exactly as production.
  Disclosed mismatch: the adapter is trained against NF4-dequantized
  weights and served on a Q4_K_M base. The comparison is therefore a
  claim about the *deployed configuration* (production base artifact +
  adapter), not about LoRA in the abstract. A merge-and-requantize
  pipeline is out of scope unless the primary serving form fails to
  load, in which case the deviation is recorded and the merged form
  becomes the measured artifact.

## Data (frozen discipline)

Three topic-disjoint partitions. **Topic-level disjointness governs**:
no proposition in train or dev may duplicate, paraphrase, or sit
adjacent to any REALWIRE / REALWIRE-T proposition (the exclusion list
is the 24 eval propositions, including both polarities of the eight
mirrored topics).

- **Train (~850 examples).** (a) The existing authored corpora —
  INDIE (144) + FREETEXT (144) + COUNTERFACTUAL (96) = 384 —
  **minus COUNTERFACTUAL tier T4 (24 items)**, whose propositions
  duplicate REALWIRE topics and are therefore excluded despite being
  authored sentences. (b) ~36 newly authored training propositions —
  examples (false: hair and nails keep growing after death; sharks
  never get cancer; alcohol kills brain cells; humans have exactly
  five senses; Edison single-handedly invented the light bulb;
  ostriches bury their heads in sand; bats are blind; touching a
  baby bird makes its mother abandon it; the five-second rule keeps
  dropped food safe; daddy-longlegs venom is the most potent of any
  spider — true: honey never spoils; sound travels faster in water
  than in air; Ada Lovelace was the first computer programmer; sea
  otters hold hands while sleeping; the dot over an "i" is called a
  tittle; wombat droppings are cube-shaped; Oxford University is
  older than the Aztec Empire). The full enumerated train and dev
  topic lists ship with the data builder and are frozen by its hash;
  no topic may appear in more than one partition. Each new
  proposition gets 12 renderings across the newsroom frame types.
  (c) ~10% distractor examples (sentence about no listed fact → the
  production no-match behavior).
  **Balance constraints (the anti-prior property):** assert/deny
  50/50; true/false propositions 50/50; stance label statistically
  independent of proposition truth across the set. Each example
  embeds a 12-proposition facts block sampled from the train pool
  with the target at a uniform random position — the adapter must
  learn the task, not one topic list.
- **Dev (12 propositions, ~144 examples).** Authored, topic-disjoint
  from train and held-out. Used ONLY for grid selection (below).
- **Held-out (12 propositions, sealed).** Authored after this freeze,
  mirroring REALWIRE construction (≈6 assert + ≈6 deny published-style
  sentences per proposition, gold by construction; 6 false / 6 true,
  famous-leaning: the O'Leary-cow Chicago fire legend; Sahara as
  largest desert; Frankenstein as the monster's name; the Amazon
  producing 20% of Earth's oxygen; "rule of thumb" wife-beating
  etymology; shaving thickens hair; the Eiffel Tower is taller in
  summer (true); bananas are botanically berries (true); Scotland's
  national animal is the unicorn (true); Cleopatra lived closer in
  time to the iPhone than to the Great Pyramid's construction
  (true); woolly mammoths were still alive when the Great Pyramid
  was built (true); Venus is the hottest planet in the solar system
  (true)). The corpus file's SHA-256
  is committed to the execution record **before training starts**;
  its sentences are never used for selection, tuning, or prompting.

**Contamination screens (run and reported before training):**
token-Jaccard overlap of every train/dev sentence against every
REALWIRE/REALWIRE-T/INDIE-eval sentence ≤ 0.80 (INDIE is train, so the
screen targets the two published corpora); topic-exclusion checklist
signed off in the execution record.

## Configuration selection (the only tuning permitted)

Grid (predeclared, 4 cells): learning rate {1e-4, 2e-4} × epochs
{2, 3}. All other hyperparameters as frozen above. Selection metric:
dev balanced accuracy = mean(assert-pool acc, deny-pool acc);
ties break to the lower learning rate, then fewer epochs. **Exactly
one** selected configuration is ever evaluated on held-out or
REALWIRE-family corpora. There is no second campaign: if the selected
adapter fails the bars, LORA-01 records KILLED and stops (a successor
study needs a new design and new authorization).

## Arms and measurement (frozen census + downstream protocol)

- **L0:** Q35A baseline, re-measured in the same session (serving
  wobble is ±1–2 items; cross-session baseline reuse is not
  permitted for the primary comparison).
- **L1:** the dev-selected adapter, served as specified above.
- Census cells (Arm A protocol): held-out (primary), REALWIRE,
  REALWIRE-T, INDIE + FREETEXT (regression guards).
- Downstream (REALWIRE newsroom seeds 0–4 × 60 steps) runs **only
  if** the primary and confirmatory census bars pass.

## Success bars and kill criteria (frozen)

- **Primary (held-out census):** assert ≥ 0.85 AND deny ≥ 0.85 AND
  |gap| ≤ 0.10 AND assert improvement over same-session L0 ≥ +0.10.
- **Confirmatory (REALWIRE census):** assert ≥ 0.88 (L0 reference
  0.797) AND deny ≥ 0.83 (no regression > 0.03 vs 0.861) AND
  |gap| ≤ 0.10. REALWIRE-T: total accuracy within 0.02 of L0
  (no-regression).
- **Regression guards:** INDIE total ≥ 0.97; FREETEXT ≥ 0.95;
  parse-failure rate ≤ 1% on every cell; abstention-equivalents
  (parse failures + no-match) ≤ 3% downstream.
- **Downstream success:** aggregate ledger error ≤ 0.28 (vs Q35A
  0.3194), supportive evidence; the census bars are decisive.
- **Kill:** primary fails → adapter KILLED as a production candidate,
  reported with the same prominence as a pass. No retuning against
  held-out signal, no reseeding, no second grid.

## Execution record requirements

Runner hash, data-builder hash, train/dev corpus hashes, sealed
held-out hash (pre-training), adapter GGUF hash, training wall time,
peak VRAM, dev-grid results for all 4 cells, and every deviation or
incident — banked in this repository alongside the results JSONs,
following the STANCE-02 record standard. Invalid runs (infrastructure
failure) are quarantined and disclosed, never averaged in.

## Estimated cost

Training data build ~1 h; grid training 4 × ~20–40 min on the
5060 Ti; census ~35 min; downstream (if gated in) ~40 min. Total
machine time ≈ 4–5 h, $0 API spend. Disk: HF base ~18 GB +
training venv ~6 GB against ~50 GB free — intermediates are deleted
as consumed; if free space falls below 8 GB the run pauses rather
than improvising.

## Authorization

Design frozen 2026-10-09 by the agent at Tristen's direction
("Design the LoRA run (frozen held-out protocol first)").
**Training launch awaits Tristen's explicit authorization.**
(Authorization was given by Tristen on 2026-10-09: "do this
training run.")

## Results — measured 2026-10-20

**Verdict: KILLED.** The selected adapter fails the frozen primary
bar, so it is not a production candidate, the downstream run does
not happen, and there is no second grid. The production default
stays Q35A (baseline prompt on Qwen3.5-9B), unchanged.

### What happened, in plain terms

The adapter learned the trained behavior well. On the sealed
held-out set — famous-leaning claims it had never seen — it raised
assertion accuracy from 0.903 to 0.972, kept denial accuracy at
1.000, and shrank the assert/deny gap from 0.097 to 0.028. On
REALWIRE (real published sentences) it also improved assertion
accuracy, 0.831 → 0.881. Two things killed it:

1. **The improvement bar was set against a weaker baseline than
   the one that showed up.** The primary bar demands an
   assertion-accuracy gain of at least +0.10 over the base model
   measured in the same session. The design expected the base
   model to score near 0.80 on held-out, as it does on REALWIRE;
   measured in-session it scored 0.903, leaving only 0.097 of
   headroom. The adapter captured 5 of the base model's 7
   assertion errors (+0.069) — even a perfect score would still
   have missed the bar. The bar is judged as frozen: missed is
   missed.
2. **On real published copy the adapter learned to abstain.** It
   answers "no listed fact" for sentences that do match a fact —
   14 of 131 REALWIRE sentences and 11 of 127 REALWIRE-T
   sentences, where the base model abstains on none. That is the
   structured protocols' failure shape (accuracy bought with
   silence), which this study existed to avoid. REALWIRE-T total
   accuracy regressed 0.929 → 0.882, outside the 0.02
   no-regression allowance, so the confirmatory bar fails as
   well.

### Dev grid (selection)

Dev balanced accuracy (mean of assert-pool and deny-pool accuracy),
in-process, 144 items per cell:

| cell | assert | deny | balanced |
|---|---|---|---|
| base (reference) | 0.986 | 1.000 | 0.993 |
| lr1e4-ep2 | 1.000 | 1.000 | **1.000** |
| lr1e4-ep3 | 1.000 | 0.986 | 0.993 |
| lr2e4-ep2 | 1.000 | 1.000 | **1.000** |
| lr2e4-ep3 | 1.000 | 1.000 | **1.000** |

Three cells tied at 1.000; the frozen tie-break (lower learning
rate, then fewer epochs) selects **lr1e4-ep2**. The dev set is
saturated — every adapter sits at or near ceiling — so selection
carried little information. That is a property of the frozen
design, recorded here rather than repaired after the fact.

### Census (one-shot, same session, Arm A protocol)

| corpus | model | total | assert | deny | gap | abstain | parse err |
|---|---|---|---|---|---|---|---|
| held-out (144) | L0 | 0.951 | 0.903 | 1.000 | 0.097 | 0 | 0 |
| held-out (144) | L1 | 0.986 | 0.972 | 1.000 | 0.028 | 0 | 0 |
| REALWIRE (131) | L0 | 0.840 | 0.831 | 0.847 | 0.017 | 0 | 2 |
| REALWIRE (131) | L1 | 0.855 | 0.881 | 0.833 | 0.048 | 14 | 0 |
| REALWIRE-T (127) | L0 | 0.929 | 0.958 | 0.891 | 0.067 | 0 | 2 |
| REALWIRE-T (127) | L1 | 0.882 | 0.972 | 0.764 | 0.209 | 11 | 0 |
| INDIE (144) | L0 | 0.993 | 1.000 | 0.986 | 0.014 | 0 | 0 |
| INDIE (144) | L1 | 0.993 | 1.000 | 0.986 | 0.014 | 0 | 0 |
| FREETEXT (144) | L0 | 1.000 | 1.000 | 1.000 | 0.000 | 0 | 0 |
| FREETEXT (144) | L1 | 1.000 | 1.000 | 1.000 | 0.000 | 0 | 0 |

Bar by bar:

- **Primary (held-out):** assert ≥ 0.85 → 0.972 PASS; deny ≥ 0.85
  → 1.000 PASS; |gap| ≤ 0.10 → 0.028 PASS; assert gain vs
  same-session L0 ≥ +0.10 → +0.069 **FAIL**. Primary fails.
- **Confirmatory (REALWIRE):** assert ≥ 0.88 → 0.881 PASS (52/59,
  one item of margin); deny ≥ 0.83 → 0.833 PASS (60/72);
  |gap| ≤ 0.10 → 0.048 PASS; REALWIRE-T total within 0.02 of L0
  → 0.882 vs 0.929 **FAIL**. Confirmatory fails.
- **Regression guards:** INDIE 0.993 ≥ 0.97 PASS; FREETEXT 1.000
  ≥ 0.95 PASS; parse failures 0% on every L1 cell PASS.
- **Downstream:** not run (gated on primary + confirmatory
  passing).

### Execution record

- Data: builder `lora01_data.py` sha256 fbb9843c…; 872 train
  examples (INDIE 144, FREETEXT 144, counterfactual T1–T3 72,
  newly authored propositions 432, distractors 80), stance balance
  396/396. Corpus hashes: train 52161f46…, dev 2f06dc74…,
  held-out 2183eb35… (sealed before training, commit a7fc674).
  Contamination screens passed: max token-Jaccard 0.278 (train)
  and 0.286 (dev) against the 0.80 bar.
- Grid training (Unsloth 2026.10.3, desktop RTX 5060 Ti):
  lr1e4-ep2 757.8 s, final train_loss 0.00410; lr1e4-ep3
  1048 s, 0.00258; lr2e4-ep2 701.8 s, 0.00514; lr2e4-ep3
  1049 s, 0.00260. Total train time 3,557 s. Trainable
  parameters 43,278,336 (0.46% of the base). GPU memory observed
  in use during training ≈ 15.9 GiB of 16 GiB.
- Winner adapter: `~/lora01/adapters/lr1e4-ep2`,
  adapter_model.safetensors sha256 c7550c6d….
- Measured artifact (L1): merged Q4_K_M GGUF, 5,780,090,496
  bytes, sha256
  7ef29b32c121885dc5c36a87839890ff2f818e06af15653cfb04919128ef927d.
- Runners (sha256 prefixes): lora01_train_unsloth.py aaef26b1…,
  lora01_devcensus.py 6a6684dc… (post-fix), lora01_merge.py
  81e7a921…, lora01_census.py 3d7680c9…, stance02.py
  6cad1c71…, newsroom.py 52fe246d….
- Results files (full sha256): lora01_dev_results.json
  70ea3477b7b66fa9c2a8554d2630411c3746fd3c978d12aff3602eb074f8682a;
  lora01_census_L0.json
  e5ce1dd589859a326872263538a9c63d1d73b0bdd334ce244a532f1ff686367e;
  lora01_census_L1.json
  e295049d49d0a0cf837ff35e70a1eaaa096bccd36887e4f92124fe5231b386bb.
- Serving: llama.cpp b11081, config N (ctx 8192, parallel 4),
  alias qwen3-8b-local, thinking disabled. L0 = production GGUF;
  L1 = merged GGUF. Each server's identity was verified from its
  /v1/models response (parameter count and artifact size) before
  its census ran. Census wall time ≈ 259 s (L0) and ≈ 257 s (L1)
  across the five corpora.

### Deviations and incidents (all disclosed)

1. **Trainer implementation.** The design froze hyperparameters,
   not an implementation. The HF Transformers trainer was
   profiled infeasible on this hardware (≈950 s/step in a 6-step
   smoke that took 5,721 s; the cost sits in BF16 GEMM kernels on
   the Blackwell card). Training ran under Unsloth with identical
   frozen hyperparameters (≈13 s/step).
2. **Serving form.** Converting the adapter to a standalone GGUF
   fails on this architecture's fused linear-attention tensors
   (llama.cpp's converter raises NotImplementedError), for
   adapters from both trainer implementations. The design's
   named fallback applies: the winner was merged into the base
   weights and the merged model quantized to Q4_K_M. Quantization
   noise therefore applies to base+delta jointly rather than to
   the base alone; the merged GGUF is the measured artifact.
3. **Warmup.** The frozen warmup ratio 0.03 was implemented as
   explicit warmup_steps (the installed transformers version
   dropped warmup_ratio); the effective schedule is unchanged.
4. **Dev census attempt 1 crashed** (2026-10-20) while loading
   the second cell: the runner released the previous model
   without a garbage-collection pass, the base model stayed
   resident, the loader offloaded modules to CPU, and the 4-bit
   loader refused. Fixed by collecting garbage between cells (the
   fix is in the committed runner). Attempt 1 was quarantined and
   the census rerun in full; the rerun's base cell reproduced
   attempt 1's base cell exactly (balanced 0.993), and no
   selection input came from the crashed attempt.
5. **Baseline reference drift.** The confirmatory bar cites a
   0.797 REALWIRE assert reference from the proof-package
   session; the same-session L0 measured 0.831, within the known
   ±1–2 item serving wobble. All bars were judged against the
   same-session L0, as the frozen protocol requires.
6. **Infrastructure.** A host-level write restriction on the
   agent's VM (2026-10-20, roughly 07:43–09:05 EDT) broke local
   git writes and the desktop-relay client mid-session; desktop
   work continued through the relay protocol's GitHub-API path.
   No measurement process was affected — training, censuses, and
   servers all ran on the desktop — and no data was lost.

### What this means

The idea behind the study — that the base model's remaining
stance errors are a learnable prior problem — is partly
supported: on held-out authored claims the adapter removed most
of the assertion error and nearly all of the assert/deny gap. But
as a production candidate under the frozen bars it fails, and the
abstention it learned on real published copy is a new cost the
baseline does not have. The lessons a successor study would start
from: improvement bars must be set against the measured
baseline's actual headroom, and distractor training data teaches
an abstention that transfers to real copy. A successor needs a
new design and new authorization; this line stops here.
