# STANCE-02 — Prior interference or parse failure? A frozen diagnostic
study of stance extraction on contested real-world copy

**Status:** FROZEN at the commit that adds this file. Hypotheses,
arms, criteria, datasets, exclusions, metrics, and decision rules
recorded here do not change after results are seen.
**Results:** MEASURED 2026-10-04/06 — see the Results section at the
end of this document.
**Predecessor:** STANCE-01 (measured 2026-10-02): on verbatim published
copy about famous falsehoods, the local extractor answered "is this
content true?" instead of "what does this sentence claim?" (assert
pool 0.034); a stance-lock prompt shifted the answer threshold rather
than teaching stance (assert 0.915 / deny 0.431); a quote-then-
classify arm amputated negation (deny 0.403 even on neutral copy).
**Governing question:** is stance failure on contested propositions
caused by world-knowledge priors interfering with discourse-level
speaker-commitment classification — and can a mechanism that never
lets the two judgments touch recover two-pool stance fidelity?

## Central hypothesis

**STANCE-H1:** Stance failure on contested propositions is primarily
caused by interference from proposition-level world-knowledge priors
with discourse-level speaker-commitment classification, rather than
by failure to parse negation or to identify proposition identity.

Broader form, also on trial: LLMs may become *worse* at identifying
what a sentence says when strong learned knowledge about what the
sentence is about interferes with discourse-level interpretation.
This study is designed so that hypothesis can fail.

Evidence that would SUPPORT STANCE-H1: topic extraction stays correct
while stance fails; matched syntax succeeds on invented/obscure
propositions and fails increasingly as proposition familiarity rises;
masking proposition identity restores stance accuracy; structured
discourse judgments reduce assert/deny bias.

Evidence that would REFUTE or weaken it: masking produces no material
improvement; unfamiliar propositions fail at similar rates; errors
track linguistic structure rather than proposition identity; frontier
models show the same failure profile under every representation.

## Target behavior

Two-pool stance fidelity on contested real copy: assertions of false
propositions recognized as assertions, denials/debunkings recognized
as denials, and the same for true propositions. A mechanism does not
count as working if it performs better mainly when the sentence
agrees with the model's prior. Aggregate accuracy never substitutes
for per-pool results.

## Datasets (frozen)

- **REALWIRE** (false propositions, verbatim published copy, 131
  sentences): `prototype/validation/realwire_corpus.py`,
  sha256 `3925ee1cb0b7153aef13da0629e1391faafb998ecd7c78cd23ed4b421e064f35`.
- **REALWIRE-T** (true propositions, verbatim published copy, 127
  sentences; climate deny pool empty by the record, not by choice):
  `prototype/validation/realwire_t_corpus.py`,
  sha256 `fb948fa6e46720488dd8ab52968f0d6320fbfe2529411c2e11566b382e1f9919`.
- **INDIE** (prior-neutral authored control, 144 sentences):
  `prototype/validation/indie_corpus.py`,
  sha256 `58fc4a0b1422cdcbdd4acf2b35fda8ef378a755ea29ff3789a0f0b599fa0617b`.
- **COUNTERFACTUAL** (authored for this study, familiarity gradient):
  16 propositions × 6 frames = 96 sentences, gold stance by
  construction. Tier 1 invented (Lake Morven's 73 islands; Tarnwick's
  mayoral lottery; the Zorvane comet's 41-year return; Millbrook
  library's Sunday-only winter hours). Tier 2 obscure real (Lake
  Baikal fresh water — true; Ulaanbaatar as Kazakhstan's capital —
  false; octopuses' three hearts — true; Porto as Portugal's
  capital — false). Tier 3 moderately familiar myths, all false
  (goldfish three-second memory; horned Viking helmets; knuckle-
  cracking arthritis; Napoleon's exceptional shortness). Tier 4
  famous contested, all false, drawn from REALWIRE for continuity
  (10-percent-of-brains; flat Earth; vaccines-autism; Great Wall
  visibility). Frames per proposition: three assert-side (plain
  assertion; confirmed-report assertion; first-person conviction) and
  three deny-side (direct denial; despite-claims debunk; corrective-
  myth denial), held as syntactically constant across propositions as
  the content allows. Known confound, disclosed in advance: fame
  tier correlates with falsity at tiers 3–4 (contested fame attaches
  to falsehoods); the gradient is corroborating evidence, and the
  masking arm is the cleaner causal lever. No causal claim will be
  made beyond what the matched design supports. The corpus file is
  committed before any run touches it and its hash recorded in the
  results provenance.
- **SKELETON masks:** masked variants of every REALWIRE and
  REALWIRE-T sentence, constructed once (model-assisted masking pass,
  then a human QC read-through of every mask with fixes recorded in
  the file) and frozen as a data file before any stance run. Frozen
  exclusion rule, stated before masks exist: a sentence whose entire
  content is the proposition itself (no discourse frame remains after
  masking) is marked degenerate, excluded from skeleton scoring, and
  listed by index in the results.

Production machinery reference: `prototype/validation/newsroom.py`,
sha256 `52fe246d8a4e38ac04113f719819abef37be657782d4eae2e1013fd91b137401`
at freeze time. The baseline extractor and prompt are whatever that
file defines; arms that modify behavior do so in the study runner,
never by editing production code mid-study.

## Arms

**Arm A — frozen baseline.** Production `LocalExtractor`, unchanged,
thinking disabled, temperature 0. Continuity reference with
STANCE-01 Arm A (which measured REALWIRE 62/131, REALWIRE-T 115/127,
INDIE 140/144).

**Arm B — baseline + reasoning.** Production prompt verbatim; only
the completion configuration changes: thinking enabled,
max_tokens 12000, server in the thinking configuration (below).
Response parsing: the last JSON object in the response that parses
and carries the required keys. Trace lengths recorded. This arm
tests whether stance is a latent judgment capability suppressed by
treating extraction as a parse task (the LOCAL-CONSOLIDATION-01
diagnosis). Whether reasoning improves fidelity, merely rationalizes
priors, or adds failure modes is an outcome, not an assumption.

**Arm C — discourse-act decomposition + symmetric probing, no
reasoning.** Three calls per sentence, complete sentence in context
throughout; the model never emits a binary stance directly.
- Call 1 (topic + act): the facts list and the sentence; returns
  `{"fact": <index or -1>, "discourse_act": <one of: direct_assertion,
  direct_denial, attributed_assertion, attributed_denial,
  debunking_corrective, discussion_no_commitment, uncertain_other>,
  "proposition_attributed_to_other": <yes|no|unclear>,
  "corrective_or_debunking_act": <yes|no|unclear>}`.
- Call 2 (probe P): the sentence and the chosen fact's proposition;
  asks whether the WRITER personally commits to the proposition's
  truth (as distinct from reporting another's view, and as distinct
  from whether the proposition is actually true); returns
  `{"answer": <yes|no|unclear>, "confidence": <0..1>}`.
- Call 3 (probe not-P): mirror of call 2 for the proposition's
  negation.
If call 1 returns fact −1, the item ends as ABSTAIN (topic) and the
probes are skipped. Any parse failure in any call ends the item as
ABSTAIN with an error flag (scored not-correct, reported separately).
Final stance is derived by the deterministic table under
"Structured derivation" — never by a further model judgment.

**Arm D — Arm C with reasoning.** Identical calls, prompts, and
derivation, with thinking enabled (thinking server configuration).
Each call additionally instructs: reason only about the sentence's
wording, structure, and who commits to what; do not reason about
whether the proposition itself is true or false. The structured
fields remain the only machine-read output.

**Arm E — hosted frontier control.** Model `gpt-5.5-2026-04-23`
(dated snapshot, via the project's OpenAI credential), temperature
0, `reasoning_effort: "none"` (verified acceptable to the API before
freezing), same response-parsing rules as the corresponding local
arm. Two protocols: E-A = the baseline protocol (Arm A's prompt);
E-C = the structured protocol (Arm C's calls and derivation). This
arm is a capability ceiling and control, not a production candidate
by default. Token usage and cost recorded per cell.

**Arm S — STANCE-SKELETON (proposition masking).** A pipeline, each
stage measured separately for error and latency:
1. Topic: production extraction on the ORIGINAL sentence; only the
   fact index is taken (its stance output is recorded for stage
   analysis but discarded for the pipeline verdict).
2. Stance: a single-proposition classifier over the MASKED sentence:
   "A claim, called Proposition X, is discussed in this sentence:
   `<masked>` — does the sentence assert that Proposition X is TRUE,
   or that it is FALSE, or neither? Return ONLY JSON:
   `{"stance": "TRUE"|"FALSE"|"NEITHER"}`." Thinking disabled,
   temperature 0.
3. Recombination: topic from stage 1, stance from stage 2 (TRUE →
   ASSERT, FALSE → DENY, NEITHER → ABSTAIN).
Stage attribution of errors: topic-stage error if stage 1's index is
wrong; stance-stage error if the index is right and the stance is
wrong; abstentions reported per stage. Degenerate-mask sentences are
excluded per the frozen rule above.

**Counterfactual evaluation.** The COUNTERFACTUAL corpus is run under
Arm A (primary readout: stance accuracy by tier and side, against
the corpus's own 16-proposition facts list), Arm C, and Arm S
(masks for these sentences are authored directly, since the
proposition spans are known by construction). STANCE-H1 predicts:
near-ceiling accuracy at tier 1, degradation concentrated in
assert-side accuracy for false propositions as tier rises, and a
flatter gradient under Arm S if masking removes the interference.

## Structured derivation (Arms C, D, E-C) — frozen

From (writer_commits_P, writer_commits_not_P), each yes/no/unclear:

| commits_P | commits_not_P | final_stance |
|---|---|---|
| yes | no | ASSERT |
| no | yes | DENY |
| no | no | NEITHER |
| yes | yes | ABSTAIN (incoherent pair) |
| any | unclear | ABSTAIN |
| unclear | any | ABSTAIN |

The discourse_act and attribution/corrective fields do not override
the derivation; they are recorded for analysis (e.g., a NEITHER
derived on a debunking-act sentence is flagged in analysis, and its
stance remains NEITHER).

## Scoring — frozen definitions

For every arm × corpus cell, one run, no retries of answered items:
- **Pool accuracy (primary):** correct / pool size. Correct = topic
  index right AND final stance equals the pool's gold stance
  (ASSERT for assert pools, DENY for deny pools). ABSTAIN, NEITHER,
  topic abstentions, and errors all count as not-correct in this
  primary metric and are itemized separately.
- **Coverage:** fraction of items whose final stance is ASSERT or
  DENY with a topic index (i.e., not abstained).
- **Conditional accuracy:** correct / covered items, with the
  complementary **error rate among covered** reported alongside.
- **Abstention rate** per pool and per corpus (and by familiarity
  tier on COUNTERFACTUAL).
- **Bias gap:** |assert-pool accuracy − deny-pool accuracy| within
  each corpus, computed on primary accuracies.
- **Per-fact accuracies** for every cell (continuity with STANCE-01;
  the 10-percent-brains, 2020-election, and Obama/Kenya facts are
  diagnostic examples, never tuning targets).
- **Latency:** mean and total wall time per call/stage; **cost:**
  hosted token usage and USD per cell.
- INDIE is scored identically and serves as the control.

## Frozen success criteria (per mechanism, both real corpora)

- REALWIRE assert ≥ 0.80 AND deny ≥ 0.80
- REALWIRE-T assert ≥ 0.80 AND deny ≥ 0.80
- INDIE total ≥ 0.95
- Bias gap ≤ 0.10 within each real corpus

All four must hold. This shape deliberately rejects threshold-shift
solutions (STANCE-01 Arm B would fail it on the deny pools and the
gap). No aggregate-only success claims.

## Downstream ledger payoff — frozen

Each candidate mechanism (B, C, D, S, E-A) is also run as the
extractor for the REALWIRE newsroom (Part 2 protocol identical to
REALWIRE-01: seeds 0–4 × 60 steps, same sources, flips, and scoring;
abstaining extractions are dropped through the newsroom's existing
out-of-range path and counted as drops, so coverage loss is visible
in the trial record). Arm A's downstream reference is REALWIRE-01's
measured **0.4637** (not re-run). Interpretation bands, frozen:
< 0.40 minimum downstream success; ≤ 0.30 meaningful system
improvement; ≤ 0.20 strong success. Mechanisms are compared on the
combination of balanced stance fidelity, downstream error,
abstention behavior, held-out generalization, and operational cost —
an arm does not become the production recommendation merely by
clearing 0.80.

## Held-out propositions and the LoRA gate

No learned or tuned mechanism is in STANCE-02's primary scope. If
one is ever proposed on the back of these results, it must be
evaluated on fresh propositions split by topic (never sentences of
known propositions), including famous falsehoods absent from all
training and prompt-development material. LoRA work does not begin
unless STANCE-02 shows all three: (1) the hosted control
demonstrates the skill is achievable; (2) local structured methods
still materially underperform; (3) the remaining gap looks learnable
rather than architectural. A tune that performs only on known
proposition families is a failure by definition.

## Execution sequence (frozen; deviations documented in results)

1. Arm A reproduction (all corpora).
2. Arm B (thinking server configuration).
3. Arm E-A hosted baseline control.
4. Arm S skeleton (mask construction + QC precede its runs).
5. Arm C structured, no reasoning.
6. Arm D structured with reasoning (thinking configuration).
7. Arm E-C hosted structured.
8. Counterfactual gradient analysis (A, C, S on COUNTERFACTUAL).
9. Downstream payoff runs.
10. LoRA decision, only via the gate above.

Server configurations: N = ctx 8192, parallel 4 (arms A, C, S, and
counterfactual non-thinking runs); T = ctx 16384, parallel 1, the
configuration LOCAL-CONSOLIDATION-01 validated for thinking work
(arms B, D). The configuration each cell ran under is recorded in
its provenance.

## Interpretation partitions (frozen readings)

- A fails and B succeeds → stance was latent local capability
  suppressed by the parse-task protocol.
- E succeeds and B fails → primarily a local capability gap.
- S or C/D succeed locally → primarily a task-representation /
  prior-interference problem (supporting STANCE-H1 by the masking
  or gradient evidence respectively).
- All representations fail locally and hosted → prioritize
  system-level reliability engineering over extractor prompting.
- No extractor reaches the criteria but abstention reliably flags
  the dangerous cases → ledger-level mitigation is a valid success
  path, and the report must say so plainly.

## System-level fallback (in scope if the criteria fail)

Provenance-tagged extractor reliability (globally and per topic),
corroboration requirements for contested propositions, forced
abstention under measured high-risk conditions, multiple independent
stance judgments where justified, and ledger rules preventing weak
stance extractions from hardening into asserted knowledge. The
objective is a trustworthy epistemic system, not loyalty to one 8B
extractor.

## Governance and provenance

One run per cell; a crashed cell is relaunched from checkpoint and
the incident disclosed (the REALWIRE/STANCE-01 convention). Failed
arms and negative results are preserved verbatim in the results file
and report; nothing is overwritten by a later success. Every cell
records: runner file hash, prompt texts (the runner is committed
before runs; its hash is the prompt provenance), model identity and
file/API snapshot, reasoning setting, decoding settings, server
configuration, dataset hashes, pool definitions, the derivation
table version (this document), abstention rules, and the ledger
scoring method (REALWIRE-01 Part 2, unchanged). AEE assesses bounded
claims only: a passing assessment does not upgrade experimental
evidence into stronger proof than the data supports. The closing
report covers every arm, the four primary pools, the INDIE control,
bias gaps, abstention metrics, per-fact results, the familiarity
gradient, downstream ledger error, latency and cost, interpretation
against the partitions above, falsified/supported hypotheses, a
recommended production mechanism with its remaining uncertainty —
and states plainly if the honest recommendation is the system-level
fallback.

---

## Results (measured 2026-10-04/06)

Census: 23/23 cells, one run each, from `stance02_results.json`
(merged key-union of the desktop and VM result files, commit
`a931304`). Downstream: `stance02_downstream_results.json` (commit
`779f47b`). Arm A reproduces STANCE-01 (REALWIRE 0.481 vs 0.473/0.481
across studies) — continuity confirmed; temperature-0 serving wobbles
±1–2 items across server restarts, recorded in STANCE-01 and visible
again here.

### Verdicts vs the frozen criteria

Frozen bars (per real corpus): assert ≥ 0.80 AND deny ≥ 0.80, INDIE
≥ 0.95, |assert−deny| gap ≤ 0.10. **Only Arm EA (hosted frontier,
baseline prompt) meets them**: REALWIRE 0.977 (assert 0.983, deny
0.972, gap 0.011), REALWIRE-T 0.961 (1.000 / 0.909, gap 0.091), INDIE
1.000. Every local arm fails the census bars:

- **A (baseline):** 0.481 / 0.906 / 0.972 (assert 0.051 on REALWIRE).
- **B (baseline + thinking):** 0.641 / 0.882 / 0.993. The false-corpus
  assert pool rises 0.051 → 0.390, but the gap stays 0.457 and the arm
  adds an unparseable-trace error mode (~2.5%, 10 items) that A lacks.
- **C (structured, no thinking):** 0.321 / 0.583 / 0.646 raw, at
  coverage 0.344 / 0.606 / 0.646 and **conditional accuracy 0.933 /
  0.962 / 1.000**.
- **D (structured + thinking):** 0.405 / 0.575 / 0.590, conditional
  accuracy **1.000 on all three cells** — every committed verdict
  across 402 items was correct.
- **S (skeleton/masking):** 0.417 / 0.173 on reduced denominators
  (47 and 52 sentences excluded as degenerate under the frozen rule —
  after full masking no stance-bearing frame remains; ~⅓ of published
  sentences carry stance only inside proposition content, so masking's
  ceiling on real copy is structural). Stage decomposition: topic
  stage near-perfect (0.93–1.00); masked-stance stage carries the
  failure (0.449 REALWIRE / 0.176 REALWIRE-T on topic-correct items).
  Denial frames survive masking (morphological stance); assertion
  frames read non-committal once masked.
- **EC (hosted structured):** 0.725 / 0.803 / 0.729 — fails on
  coverage (0.748–0.811) with conditional accuracy 0.969 / 0.990 /
  1.000. Its failure mode is NEITHER verdicts, not errors (INDIE:
  coverage == accuracy, zero committed errors).

Per-fact: no single fact drives the REALWIRE results (Arm A is
uniformly ~0.4–0.6 per fact). EA's weakest cell is REALWIRE-T fact 12
("World War II ended in 1945", 7/10) — the legal-formal deny items
trip even the frontier model.

### STANCE-H1: supported in mechanism, with a refinement

Three independent lines: **(1) Dose-response** — Arm A assert
accuracy falls monotonically with proposition familiarity on
syntax-matched authored frames: invented 1.000 → obscure 0.750 →
moderate myth 0.417 → famous contested 0.167. **(2) Representation
flip** — Arm C's familiarity gradient is flat (assert T4 0.833 vs
A's 0.167; totals 0.83–0.96 across tiers): decomposing the task into
writer-commitment probes abolishes the familiarity effect wherever
the protocol gets traction. **(3) Masking** flattens the deny side
entirely (1.000 on surviving frames) and halves the assert-side
gradient. The failure is not negation parsing (the deny side is
healthy in the baseline: 0.833–0.875) and not proposition identity
(topic ID ≥ 0.93 wherever measured separately). It is prior
interference with the stance judgment, and it is
representation-sensitive. **Refinement:** at 8B scale a second,
independent failure family dominates the structured arms' raw
scores — protocol execution (next section) — which is not prior
interference and must not be conflated with it.

### The structured protocol's three coverage sinks

1. **Call-1 topic abdication.** The compound first call (fact + act
   + attribution + corrective in one JSON) returns fact −1 on
   17–34% of local items (EC: 3%), including items it simultaneously
   labels `direct_assertion`; the probes then never run. When call 1
   names a fact it is essentially always right (wrong-fact 0–2 per
   cell). Largest local sink on REALWIRE.
2. **NEITHER from commitment strictness.** The probes measure
   *writer commitment*; reported speech scores (no, no) → NEITHER.
   Dominant sink at frontier scale (EC INDIE 38) and for D (INDIE
   53). A task-definition choice — writer commitment is stricter
   than sentence stance — not a capability failure.
3. **Unclear/incoherent probes.** Small everywhere (0–24 per cell).

Because everything surviving all three gates is easy, conditional
accuracy is 0.93–1.00 for C, D, and EC alike. The protocol converts
the baseline's wrong answers into silence; it does not convert them
into coverage.

### Downstream payoff (REALWIRE newsroom, seeds 0–4 × 60 steps)

Reference: REALWIRE-01 local baseline ledger error 0.4637. Frozen
bands: < 0.40 minimum, ≤ 0.30 meaningful, ≤ 0.20 strong. Abstentions
are dropped by ingest and counted.

- **EA: ledger 0.1802 — STRONG band.** Naive (same extractor) 0.2215;
  ledger derived 0.1842 vs naive derived 0.3492; seeds 0.159–0.215;
  0 abstentions in 4,920 calls. End-to-end error falls 61% vs the
  reference. Note the compression: with near-perfect extraction the
  ledger-vs-naive gap narrows, because there is little noise left to
  absorb — the gain is extraction's.
- **B: ledger 0.4169 — FAILS the minimum band.** Naive 0.4233;
  derived 0.3783 / 0.4042; seeds 0.286–0.517 (high variance); on
  seeds 0–1 ledger and naive are identical. Thinking alone is not a
  downstream mechanism.
- **C: ledger 0.3994 — meets the minimum band by 0.0006, stated
  plainly: at the line, not comfortably inside it.** Naive 0.4258;
  derived 0.3567 vs naive 0.4625 — the clearest ledger-over-naive
  derived gain of any local arm; seeds 0.286–0.578; abstentions
  608–667 of 984 per seed (62–68%). Silence costs coverage but what
  survives is reliable, and the ledger exploits exactly that.
- **S: ledger 0.4690 — FAILS all bands**, worse than the 0.4637
  reference and worse than its own naive (0.4635); abstentions
  707–764 of 984 (72–78%). Masking starves the ledger: at
  three-quarters of the wire dropped, bookkeeping has too little to
  work with.
- **D: downstream INCOMPLETE at report close.** D's census verdict
  is complete (above). Its downstream run is the slowest cell in the
  study (24–26 s/item census latency; projected 35–55 h for five
  seeds) and was sequenced last by an execution decision recorded
  during the run; it is executing under config T after a corrected
  false start (incident 4). Per that decision the study closes
  without it rather than holding the report hostage; its number,
  when it lands, will be appended as a dated addendum.

### Interpretation vs the frozen partitions

- *"S or C/D succeed → task-representation / prior interference
  (supports STANCE-H1)"*: fires at the mechanism level — flat
  gradient, perfect conditional accuracy — with a capability caveat
  at 8B on raw fidelity.
- *"E succeeds + B fails → local capability gap"*: also fires, for
  the product-level two-pool fidelity target (EA passes every bar;
  no local arm does).
- Both partitions fire because they concern different quantities
  (mechanism vs product fidelity). 
- *"None reach criteria but abstention reliably flags dangerous
  cases → ledger-level mitigation is a valid success path"*: true
  for the local line, and it is the operative recommendation below.

### LoRA gate (frozen three conditions)

(1) Hosted control demonstrates the skill is achievable: **MET**
(EA). (2) Local structured methods still materially underperform:
**MET** on raw fidelity; **NOT met** on conditional fidelity.
(3) The gap looks learnable, not architectural: **PARTIALLY
supported** — sinks 1 and 3 are format/protocol-shaped and plausibly
learnable; sink 2 is a definition, not a deficit, and no training
fixes a definition. No LoRA is launched by this study; a proposal
would need owner authorization and the frozen held-out discipline
(fresh propositions split by topic, famous falsehoods never in
training material).

### Production recommendation

Per the frozen rule (do not freeze an architecture merely for
clearing 0.80), the recommendation is layered:

- **Default extraction stays the local baseline** (0.27 s/item, $0),
  its outputs on contested material treated as provisional evidence
  — STANCE-01's standing rule, now with a measured familiarity
  gradient behind it.
- **The structured protocol (C-shape) is the escalation path** for
  contested or high-stakes items: committed verdicts are 0.93–1.00
  accurate at every scale tested, and its abstentions are safe
  (dropped, counted). Its production form should split call 1
  (topic via the proven baseline extract; probes separately) to
  attack sink 1 — that variant is UNMEASURED and is STANCE-03
  material, not a claim of this study.
- **Frontier extraction (EA-shape) is the measured ceiling** and
  the only configuration in the strong downstream band; where
  hosted calls are acceptable it is the only arm that meets every
  frozen bar.
- **Ledger-level mitigations stand regardless of extractor**:
  provenance-tagged reliability, corroboration requirements for
  contested propositions, forced abstention under measured
  high-risk conditions — the fallback named in advance, and for a
  local-only deployment the honest primary answer.

### Incidents (all disclosed; invalid runs quarantined, never averaged in)

1. First masking launch ran against a dead llama-server (its fourth
   silent death): 354/354 masks were connection-refused; wiped and
   relaunched clean after restart.
2. The first B/D downstream attempt crashed with zero seeds banked:
   Arm B's adapter let a ~2.5% unparseable-completion rate kill
   whole seeds, and the server then segfaulted mid-D (fifth death;
   backtrace preserved in the server log). Fix (commit `be2de67`):
   adapters guard extraction exceptions into the drop sentinel, per
   the runner docstring's own specification; prompts, derivation,
   seeds, and bands untouched. Both arms rerun from empty
   checkpoints.
3. Desktop-relay congestion repeatedly hid run state (up to ~2 h);
   runs were unaffected (nohup + checkpoints throughout).
4. D's downstream relaunch on 2026-10-06 initially ran ~15 minutes
   against the wrong server configuration (config N instead of T)
   after a process-kill pattern failed to match the running server.
   Nothing was banked; the run was discarded, the server relaunched
   under config T and verified from its startup log
   (`n_slots = 1, n_ctx_slot = 16384`), and D restarted from an
   empty checkpoint.

### Cost / latency

All local arms $0. EA census: 88,600 input / 5,628 output tokens
(well under $1). EC census call-1 usage 147,292 in / 14,644 out
(partial metering — probes unmetered). EA downstream: 4,920 calls,
~1.6 h wall. Mean latency per census item: A 0.27 s, S ~0.47 s,
C 1.3–1.5 s, EA 1.4–1.6 s, EC 4.2–4.5 s, B 4–11 s, D 24–26 s — the
thinking arms cost 15–100× the baseline's latency for their gains.

### Post-freeze developments (NOT STANCE-02 results)

Recorded here so the closing state of knowledge is in one place;
neither changes any verdict above.

- **Model-fold bench (2026-10-05/06):** the frozen census protocol
  (arms A + C) run against four other local models. Qwen3.5-9B leads
  every cell (A: 0.832 / 0.929 / 0.993; its REALWIRE assert pool is
  0.797 with gap 0.065 — the famous-falsehood failure largely
  disappears with zero protocol changes, missing the frozen assert
  bar by one item, inside the ±1–2 item serving wobble). Its Arm C
  coverage roughly doubles the incumbent's at conditional accuracy
  0.99–1.00 — sink 1 is partly a model-generation property.
  Llama-3.1-8B posts the most balanced baseline (REALWIRE gap
  0.002); Mistral-7B shows the opposite pathology (a yes-bias, deny
  pools ~0.11); Gemma-2-9B is assert-strong (0.949) with deny lag.
  Arm C conditional accuracy is ~1.0 on every model — the
  derivation gate behaves model-independently. Full table:
  `fold_results_*.json` (commit `689851a`). Consequence for the
  production recommendation: a base-model upgrade is now the
  strongest single lever on the local line, ahead of protocol work.
- **Classical baseline (fastText, commit `b49cd99`):** a supervised
  bag-of-ngrams classifier trained on the 384 authored sentences,
  stance given gold topic, scores 0.618 on REALWIRE — above
  Qwen3-8B's stance-stage accuracy conditioned on correct topic
  (0.516) — and 0.512 on REALWIRE-T (LLM: 0.920). A pair-formulated
  variant (fact + sentence jointly) is weak throughout: relational
  matching defeats a linear ngram model. The classical floor
  confirms the false-corpus stance task is not intrinsically hard;
  the incumbent model's failure on it is a prior-interference
  effect, not task difficulty.
