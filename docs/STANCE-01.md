# STANCE-01 — Does the extractor report the sentence, or its own beliefs?

**Status:** OPEN — design frozen at the commit that adds this file.
Corpus sourcing is step 1; no arm has been run.
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
