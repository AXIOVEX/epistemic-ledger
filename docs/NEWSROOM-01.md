# Newsroom experiment: integrated adversarial validation

**Date:** 2026-10-02. **Status:** measured.

Prior validations were single-feature or toy. This one exercises the full
v0.6 feature set *together* against the program's core thesis: a
ledger-backed memory beats frozen memory on a realistic, adversarial,
multi-source belief stream.

## Design

`prototype/validation/newsroom.py`. 12 fictional-news facts flip over
60 steps (p=0.04). Six sources report in natural-language sentences
(template registry; modeled extraction — this tests belief-structure
dynamics, not NLP):

| source | tier | true accuracy |
|---|---|---|
| wire-a, wire-b | contributor | 0.88–0.90, honest |
| blog-c, blog-d | provisional | 0.72–0.75, honest |
| rumor-e, rumor-f | unregistered | 0.30–0.35, **adversarial** |

- One claim per ordinary fact; reports update Bayesian posterior odds
  with the source's *learned* accuracy as likelihood. Both agents share
  the accumulation math and the extraction stream — the only difference
  under test is **revision vs. frozen**.
- Contested facts (F10, F11) get per-desk assessment claims (wire-desk /
  rumor-desk) with D–S intervals — the genuine contradictions.
- Derived: noisy-and / noisy-or combos, incl. D1=AND(F1,F2) and
  D2=OR(F1,F2) over the same parents (the spurious-flag probe).
- Trust learning: reports verified against ground truth with a 10-step
  delay; per-source accuracy Laplace-smoothed toward the tier prior.
- Detection at steps 5–30; genuine desk contradictions auto-resolved,
  spurious flags counted, never resolved.
- Outcomes at 20/40/60 → `learn_entrenchment`; kill bars evaluated.

## Results (5 seeds, 960 quizzes each)

| seed | ledger err | naive err | derived ledger | derived naive | kill bars |
|---:|---:|---:|---:|---:|---|
| 0 | 0.141 | 0.222 | 0.129 | 0.454 | ok |
| 1 | 0.138 | 0.184 | 0.208 | 0.396 | ok |
| 2 | 0.170 | 0.178 | 0.167 | 0.200 | **brier trip** |
| 3 | 0.152 | 0.149 | 0.117 | 0.104 | ok |
| 4 | 0.126 | 0.183 | 0.104 | 0.333 | **churn trip** |
| **mean** | **0.145** | **0.183** | **0.145** | **0.297** | |

**Overall staleness reduction: 20.8%. Derived-only: 51.3%.** The baseline
is strong — it does full Bayesian updating and trust learning; only its
derived conclusions are frozen. The overall number is therefore the
*isolated* marginal value of the revision machinery, and it is
positive on 4/5 seeds. Seed 3 went the other way narrowly (quiet world;
frozen happened to be right).

Trust learning converged: rumor sources learned to 0.34–0.46 (true
0.30–0.35, floored by extraction noise), wire-a to 0.84–0.92. Known
liars' reports are inverted by the odds update — the correct Bayesian
response, and it dissolves desk contradictions over time.

## Findings

1. **Detection precision needed proposition identity — fixed, with a
   caveat.** Unfiltered interval-conflict flags *any* opposed decided
   pair (wire-desk F11 vs wire-desk F10 — different propositions).
   Measured pre-fix: 7 cross-fact false positives. `detect_contradictions`
   now accepts `topic_of`; with it, cross-fact FPs went to **0** and
   genuine same-fact desk contradictions still fire (5 across seeds,
   in the early window before trust learning dissolves them). The
   residual spurious class is the (D1,D2) probe: AND and OR over the
   same parents *legitimately* disagree — shared-ancestry opposition
   cannot distinguish that from contradiction without understanding
   the propositions. This is the evidence-backed case for the deferred
   **LLM consolidation pass** (Design Memo 02): proposition identity
   has to come from somewhere, and heuristics are at their ceiling.

2. **Accurate but overconfident.** Seed 2 tripped the Brier bar
   (0.29 > 0.25) at ~83% accuracy: a handful of confidently-wrong
   snapshots (0.97 vs. truth 0) after fact flips and adversarial bursts
   dominate the quadratic score. The per-report λ (6.1 for wire
   sources) makes posteriors swing hard. This is the *agent's*
   inference tuning, not the ledger's machinery — the naive baseline
   shares the same posteriors — but the ledger faithfully surfaced it,
   which is what the kill metric is for. Fact-claim Brier in a
   diagnostic run: 0.062.

3. **The churn metric conflates tracking with instability.** Healthy
   adversarial tracking produces 4–8 sign changes per 10 revisions.
   The provisional bar (4) tripped on every seed; recalibrated to 8 on
   this data, it still trips on 1/5. The metric needs to be normalized
   by evidence-conflict rate to mean what it claims to mean. Recorded
   as future work, not silently widened again.

4. **Two bugs the experiment caught in itself.** (a) `verify_trust`
   recomputed accuracy per batch instead of accumulating — trust never
   converged past the prior until fixed. (b) Both agents initially
   shared one RNG, so they *misparsed the same sentence differently* —
   an unfairness confound; extraction now happens once and is shared.
   Both are the kind of defect single-feature tests don't catch.

## What this does not establish

- Real NLP: extraction is modeled. The `LLMExtractor` stub is the swap
  point; wiring it needs an approved API spend.
- Multi-agent / multi-party behavior (signatures, partitions remain
  deferred per Design Memo 06).

## Next

The LLM consolidation pass — offline, proposition-aware contradiction
detection and consolidation (the Letta sleep-time pattern, applied to
the ledger) — is now the highest-value item, because finding 1 shows
exactly where heuristics stop.
