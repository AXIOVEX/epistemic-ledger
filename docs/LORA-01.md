# LORA-01 — stance-fidelity adapter for the production extraction path

**Status: DESIGN FROZEN 2026-10-09. Training is NOT authorized by this
document.** Launch requires Tristen's explicit authorization, per the
STANCE-02 LoRA gate. This design exists so that authorization, when
given, executes a frozen protocol rather than an improvisation.

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
