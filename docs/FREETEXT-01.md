# FREETEXT-01 — Extraction and the newsroom on free prose

**Date:** 2026-10-02. **Status:** complete. Results:
`prototype/validation/freetext_local_results.json` (commit
`f3165ba`). Corpus: `prototype/validation/freetext_corpus.py`.
Runner: `prototype/validation/freetext_local.py`. All runs $0 on the
owner's desktop (Qwen3-8B, llama.cpp, `newsroom.LocalExtractor`).

## Why this exists

Every prior NL number — NEWSROOM-01, LOCAL-EXTRACTION-01,
CONSOLIDATION-01 — was measured on the 2+2 template sentences in
`newsroom.FACTS`. This validation replaces them with authored free
prose: 144 renderings of the same 12 facts (6 true + 6 false each,
ground truth by construction, fact statements unchanged), varying
synonym, voice, attribution, apposition, and register — never
hedging the proposition itself. Anything genuinely contestable was
kept out of the scored pools and measured separately.

## Part 1 — extraction census (every sentence exactly once)

| set | n | accuracy |
|---|---|---|
| pooled free prose | 144 | **0.972** (140/144) |
| template sentences (LOCAL-EXTRACTION-01) | 200 | 1.000 |
| hard probes (scored) | 8 | 0.750 (6/8) |

All 4 pool errors are value flips; fact identification never
failed and no call raised. But the errors are **concentrated, not
uniform**: 3 of the 4 sit in one cell — fact 7's false pool, in
present-state phrasings ("Lawmakers in Vantia remain in session;
no dissolution occurred", "parliament is very much alive…",
"the legislature remains in place and in session" — all read as
TRUE). The fourth is an inference-demanding fact-0 sentence ("The
board passed over Maria Chen, keeping the role with its
incumbent" → TRUE). The extractor keys on a parliament being
active and present rather than on the dissolved/not-dissolved
distinction.

The 2 hard-probe failures share one device: **negation about
reports and belief** — "Reports that Maria Chen does not lead
AstraCorp were dismissed as baseless" (read FALSE; the dismissal
of the negation is the assertion) and "Not everyone believes the
Solstice probe landed, but the agency insists it did" (read
FALSE). Plain double negation ("It is not true that copper failed
to reach $5") and direct denial-of-claim passed.

**Distractors** (8 sentences asserting no fact) produced the run's
most unexpected datum: 6 of 8 came back mapped to **fact −1** — an
unprompted, emergent "none of these" the prompt never offers.
Only the two *entity-adjacent* distractors were force-mapped to
real facts: "Shares of AstraCorp rose two percent…" → fact 0 TRUE,
"Copper miners in Chile announced a strike…" → fact 9 FALSE. So
the forced-choice hazard is narrower than designed for, but
precisely located: entity overlap without propositional content.
Note the integration gap this exposes — the newsroom pipeline has
no handling for a −1 return (it would fail loudly on ingestion,
which is the right failure mode, but it is unhandled by design
intent nowhere). The 6 unscored observation sentences (mentions
without commitment) were all committed to some answer, as a
forced-choice contract guarantees; outputs are recorded verbatim
in the results JSON.

## Part 2 — the newsroom on free prose (5 seeds × 60 steps)

`newsroom.FACTS` rebound to the free pools; same extractor, same
seeds as LOCAL-EXTRACTION-01; 4,800 quizzes.

| condition | ledger err | naive err | eliminated | derived |
|---|---|---|---|---|
| free prose | 0.1371 | 0.1648 | **16.8%** | **43.5%** |
| templates | 0.1506 | 0.1935 | 22.2% | 60.8% |

Seed record: **3/5 wins** (templates: 5/5). Seeds 1 and 3 lose
narrowly (0.156/0.151; 0.122/0.110). Seed 4 is the widest margin
in the program's history: naive collapses (0.234 overall, derived
**0.600**) while the ledger holds 0.114 / 0.117.

**Sensitivity, stated plainly:** excluding seed 4, the aggregate
advantage shrinks to 3.0% overall and 10.5% on derived. The
five-seed headline is carried substantially by one hostile-stream
seed. Both figures are the result; neither should be quoted
without the other.

## Interpretation

1. A 2.8-point drop in parse accuracy (1.000 → 0.972) cost a
   quarter to a third of the end-to-end advantage — because these
   errors are *systematic*. A fact whose negations are misread
   half the time in one phrasing style injects coherently wrong
   evidence that trust-learning cannot average away the way it
   absorbs iid noise. Extraction-error *structure*, not just rate,
   is a load-bearing property of any real deployment.
2. What survives free prose is the ledger's insurance character:
   in the seed where the stream turned hostile, revision
   machinery was the difference between 0.114 and 0.234. In calm
   seeds the edge is thin. That is a more modest claim than the
   template runs supported, and it is the claim the evidence now
   supports.
3. Authorship caveat: the corpus was written by the same author
   as the system under test. The variety is genuine and the traps
   were planted against the extractor, but a corpus authored by
   other humans — or drawn from real wire copy with planted facts
   — is the next rung, and this report does not pretend otherwise.

## Standing caveat (unchanged)

Report streams across conditions are matched in distribution, not
identical (extractor RNG consumption differs); within-condition
ledger-vs-naive gaps are the measured claims. Absolute error
levels are not comparable across the template/free-prose rows.
