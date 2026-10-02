# STANCE-01 — Does the extractor report the sentence, or its own beliefs?

**Status:** MEASURED 2026-10-02 — H1 not confirmed as stated (the
inversion is assert-side only), H2 FAILED, Part 2 gated off and not
run. Full results at the end of this document.
**Motivating measurement:** REALWIRE-01 (2026-10-02).
**Extractor under test:** Qwen3-8B local (llama.cpp), temperature 0,
identical census machinery to FREETEXT-01 / INDIE-CORPUS-01 /
REALWIRE-01 unless an arm says otherwise.

## The finding this study follows up

REALWIRE-01 Part 1 (verbatim published copy, 12 famous *false*
propositions): accuracy 0.481. Topic identification held (9/131
fact_wrong); stance collapsed asymmetrically — **assert pool 3/59
correct (52 pure stance flips), deny pool 60/72**. The extractor's
answers track the real-world truth of the proposition rather than the
sentence's stance toward it. All 12 REALWIRE propositions are false in
the real world, so that study alone cannot distinguish "the extractor
grades against its priors" from "asserting sentences about these
topics are intrinsically harder to parse." This study distinguishes
them, and tests whether the failure is correctable at the prompt
level.

## Hypotheses and pre-stated criteria

**H1 — prior dominance (directional).** Under the baseline prompt,
the accuracy asymmetry is a function of the proposition's real-world
truth: on *true* propositions it inverts (deny pool collapses, assert
pool high).
Criterion: baseline assert-accuracy(true corpus) −
assert-accuracy(false corpus) ≥ 0.40 **and** deny-accuracy(false) −
deny-accuracy(true) ≥ 0.40. If the asymmetry does not invert, H1 is
refuted and the REALWIRE-01 failure needs a different explanation.

**H2 — stance-locking recovers fidelity.** A prompt that explicitly
instructs stance-reporting (Arm B) recovers assert-pool accuracy on
the false-proposition corpus to ≥ 0.80, while holding deny accuracy
there ≥ 0.75 and fictional-corpus (INDIE) accuracy ≥ 0.95.

**H3 — anchoring vs instruction (secondary).** A two-pass
quote-then-classify protocol (Arm C) beats Arm B on the false-corpus
assert pool if the failure is prior-driven (the verbatim quote anchors
classification to the text). If C ≈ B, the lever is the instruction,
not the anchor. No separate bar; reported as measured.

**Kill criterion for the prompt-level line.** If neither B nor C
reaches 0.60 assert accuracy on the false corpus, prompt-level repair
is recorded as KILLED for this model class; any successor must change
the model or the interface, under a new study ID.

## Corpus: REALWIRE-T (to be sourced)

12 propositions, all **true** in the real world, verbatim published
assert/deny pools, sourced under the identical protocol to
REALWIRE-01 (per-sentence outlet + URL; pools by stance; QC drops
disclosed with reasons; shortfalls reported, never filled). Frozen
list:

1. Barack Obama was born in Hawaii.
2. Joe Biden won the 2020 U.S. presidential election.
3. Apollo 11 landed humans on the Moon in 1969.
4. The Earth is round.
5. The Great Wall of China is not visible from outer space with the
   naked eye.
6. Albert Einstein did not fail mathematics as a school student.
7. Iraq did not possess stockpiles of weapons of mass destruction
   in 2003.
8. Vaccines do not cause autism.
9. Cigarette smoking causes lung cancer.
10. Humans and chimpanzees share a common ancestor.
11. Global average surface temperatures have risen since the late
    19th century.
12. World War II ended in 1945.

Facts 1–9 mirror REALWIRE-01 propositions (in true or canonical
form); 10–12 are fresh. Deny pools for settled true claims are
expected to be thin in print in places — the same scarcity phenomenon
REALWIRE-01 found on the assert side, and equally reportable. The
census metric is per-pool accuracy, defined for any non-empty pool.

## Arms (prompt texts frozen here)

All arms use the baseline fact-list format and JSON output contract
of `newsroom.LocalExtractor`. Only the instruction text varies.

**Arm A — baseline.** The current production prompt, verbatim:
"Which fact does the sentence report on, and does it assert that
fact is TRUE or FALSE? Return ONLY JSON: {"fact": <index>,
"says_true": <true|false>}".

**Arm B — stance-locked.** Arm A plus, before the question: "Report
what the SENTENCE claims, not what is actually true. A sentence can
assert a false claim; your job is to record its stance toward the
listed fact exactly as written, even when you know the claim is
wrong. Never substitute your own knowledge of the facts for the
sentence's position."

**Arm C — two-pass quote-then-classify.** Pass 1: "From the
sentence, quote verbatim the clause that takes a position on one of
the listed facts, and give that fact's index. Return ONLY JSON:
{"fact": <index>, "quote": "<verbatim clause>"}." Pass 2 (given the
fact statement and the returned quote only, not the full sentence):
"Does the quoted clause assert that the stated fact is TRUE or
FALSE? Return ONLY JSON: {"says_true": <true|false>}."

## Protocol

1. Source REALWIRE-T (step 1; QC + corpus file mirroring
   `realwire_corpus.py`, attribution included).
2. Part 1 census: arms A/B/C × corpora {REALWIRE (131), REALWIRE-T
   (as sourced), INDIE (144, control)}. One run per cell, no retries
   or prompt edits after first results (one-shot discipline; a
   crashed run is relaunched from checkpoint and disclosed, as
   before).
3. Part 2 (gated): only if H2 passes, re-run the REALWIRE newsroom
   (seeds 0–4 × 60) with the winning arm. Pre-stated expectation: if
   stance fidelity is the binding constraint, ledger error falls
   materially from REALWIRE-01's 0.4637 — bar ≤ 0.40 — with the
   excl.-seed-4 sensitivity reported alongside, as always. If H2
   fails, Part 2 does not run and the study closes on Part 1.

## What this study is not

Not a prompt-tuning sweep: three frozen arms, one run each. Not a
model comparison: one extractor, held constant, so the prompt is the
only moving part. Not a fix in search of a problem: the kill
criterion above is a real outcome this study can reach.

## Results (2026-10-02)

Corpus as sourced and QC'd: REALWIRE-T = 127 sentences (assert pools
6/6 per fact; deny pools 5, 6, 6, 6, 5, 3, 6, 6, 2, 6, 0, 4 — the
climate fact's deny pool is EMPTY because no published sentence
located flatly denies the century-scale temperature rise; the smoking
fact's deny pool is 2 after two "not proven" items were excluded at
QC as non-assertions; the WWII deny pool is legal-formal readings
only). All shortfalls and QC drops are recorded in the corpus module
header; none were filled.

Part 1 census, accuracy by pool (correct requires right fact AND
right stance; fw = fact wrong, vw = stance wrong, err = unparseable
or transport failure):

| cell | assert | deny | total | fw | vw | err |
|---|---|---|---|---|---|---|
| A REALWIRE (false) | **0.034** (2/59) | 0.833 (60/72) | 0.473 | 9 | 60 | 0 |
| A REALWIRE-T (true) | 0.958 (69/72) | 0.836 (46/55) | 0.906 | 3 | 9 | 0 |
| A INDIE (neutral) | 0.958 | 0.986 | 0.972 | 1 | 3 | 0 |
| B REALWIRE | 0.915 (54/59) | **0.431** (31/72) | 0.649 | 10 | 36 | 0 |
| B REALWIRE-T | 0.944 | **0.491** (27/55) | 0.748 | 2 | 30 | 0 |
| B INDIE | 1.000 | 0.944 | 0.972 | 1 | 3 | 0 |
| C REALWIRE | 0.475 (28/59) | 0.528 (38/72) | 0.504 | 9 | 52 | 4 |
| C REALWIRE-T | 0.931 | 0.564 (31/55) | 0.772 | 1 | 27 | 1 |
| C INDIE | 1.000 | **0.403** (29/72) | 0.701 | 1 | 42 | 0 |

Replication check: Arm A on REALWIRE re-measured REALWIRE-01's census
at 62/131 vs the original 63/131 — identical fact_wrong (9), one
additional stance flip (value_wrong 60 vs 59). Temperature-0 serving
is not bit-deterministic across server restarts; the one-sentence
drift is recorded, not averaged away.

### Verdicts, against the frozen criteria

- **H1 — NOT CONFIRMED as stated.** The assert-side gap is +0.924
  (0.958 true vs 0.034 false), far past the +0.40 bar; the deny-side
  gap is −0.003 (0.833 false vs 0.836 true) against the required
  +0.40. The symmetric inversion does not happen. What the four Arm A
  cells support instead is the mechanism in an asymmetric form: the
  extractor answers "is this sentence's content true?" and that
  heuristic coincides with correct stance extraction in three of the
  four cells — it fails exactly and only where sentences assert
  famous falsehoods. The deny-side prediction failed because deny
  sentences are scored "right" by the same heuristic on both corpora.
- **H2 — FAILED.** Arm B recovers false-corpus assert accuracy to
  0.915 (bar 0.80, met) but deny accuracy falls to 0.431 (bar 0.75,
  missed by a wide margin). The stance-lock paragraph does not teach
  stance; it shifts the says_true threshold toward TRUE — asserts are
  fixed on every corpus (0.92–1.00) and denies degrade wherever the
  model's priors are engaged (0.43–0.49 on real copy) while staying
  intact on prior-neutral copy (INDIE deny 0.944, total 0.972). Per
  the frozen gate, **Part 2 does not run**. The INDIE cells for arms
  B and C were run as diagnostics after the fact (the frozen protocol
  assigned the control to a winning arm; there was none) — they
  change no verdict and are labeled diagnostic wherever cited.
- **H3 — resolved against anchoring.** Arm C does not beat Arm B on
  the false corpus (assert 0.475 vs 0.915); it is worse than B on
  every contested cell. Worse, C fails structurally even on neutral
  copy: INDIE deny accuracy 0.403 against the baseline's 0.986. The
  quote-then-classify pass amputates negation — pass 1 quotes the
  operative clause of a denial and pass 2 judges the clause stripped
  of its negator. Anchoring is not the lever; it is an additional
  failure mode.
- **Kill criterion — NOT triggered** (Arm B assert 0.915 ≥ 0.60), but
  the substantive position is close to what the criterion was written
  to detect: no prompt arm achieves two-pool fidelity on real
  published copy about contested propositions. The best false-corpus
  joint performance (worse pool) is C 0.475 / B 0.431 / A 0.034. The
  prompt-level line stays open by the letter of the criterion; by
  its spirit, the burden of proof is now on any successor design to
  show a mechanism other than threshold-shifting or quote-anchoring.

### Run incidents

The first INDIE diagnostic attempt scored 0/144 in all three arms:
the llama-server had died after the main chain completed, and every
call returned connection-refused. Those cells were quarantined as
invalid (checkpoint keys cleared, never averaged in), the server was
restarted, and the cells were re-measured; the numbers above are the
re-measurement. The six protocol cells were unaffected — they had
completed before the failure, and Arm A's REALWIRE cell
independently replicates REALWIRE-01.

### What this means for the ledger program

Extraction from real published copy about famous propositions is the
binding constraint, and it is a *judgment* failure, not a parsing
failure (topic identification is 0.93+ throughout; stance is what
collapses). Two concrete implications: (1) an extractor's pool-
conditional error profile — near-perfect on neutral copy, inverted
on contested copy — is invisible to neutral-corpus validation, which
is why the earlier 0.97s did not predict REALWIRE; validation corpora
for extraction must include famous-falsehood material as a matter of
course. (2) Until an extractor reads stance rather than plausibility,
the ledger's correct posture on contested real-world input is the
one it already has: treat extracted stances on such material as
provisional evidence with wide uncertainty, never as ground truth.
