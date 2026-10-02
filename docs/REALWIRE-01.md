# REALWIRE-01 — Verbatim published copy: extraction census and newsroom

**Date:** 2026-10-02. **Extractor:** Qwen3-8B (llama.cpp, local, owner's
desktop), identical protocol to FREETEXT-01 and INDIE-CORPUS-01.
**Corpus:** `prototype/validation/realwire_corpus.py`.
**Runner:** `prototype/validation/realwire_local.py`.
**Results:** `prototype/validation/realwire_local_results.json`.

## Why this corpus exists

FREETEXT-01's caveat (author = system author) was retired by
INDIE-CORPUS-01 (author = gpt-4.1). Both still measured extraction on
*sentences written for the test*. REALWIRE-01 removes the last
authorship degree of freedom: every sentence is verbatim published
copy — news, wire, reference, book, and periodical text — asserting or
denying 12 real-world propositions (the 1948 Dewey headline, the hacked
AP tweet, the 2020 election, Apollo, flat Earth, the Great Wall,
Einstein's math grades, Iraq WMD, vaccines, Elvis, the 10% brain
myth, Obama's birthplace). All 12 propositions are, in the real world,
false; pool assignment is by the sentence's stance, not by truth,
exactly as in the earlier corpora.

## Corpus construction and QC

Sentences were sourced by three web-research passes with per-sentence
outlet + URL attribution (carried in `REALWIRE_ATTRIBUTION`).
Labeling/QC is the system author's, disclosed here. QC rule: a pool
sentence must itself take the asserting/denying stance (in its own
voice or as an attributed claim with the proposition as content).
**13 of 144 sourced sentences were dropped** (listed with reasons in
`REALWIRE_DROPPED`): fact 3 ×4 (three meta-reports of the claim's
existence/history and one item framing the embedded claim as fake),
fact 6 ×2 and fact 7 ×3 (sentences whose own frame — "The Lie:",
"misconception", "the story asserts", "a prevailing myth" — takes
the opposite stance or no stance), fact 10 ×2 (an interpretation of
a book/album release and a song's narrative suggestion), and the two
Wakefield-era vaccine items (fact 9 ×2), which assert non-use of the
combined MMR and the safety of separate administration but never
mention autism or causation.

Kept: **131 sentences** — assert pools 6,6,6,2,6,6,4,3,6,4,4,6 (59),
deny pools 6 per fact (72). The shortfalls are properties of the
published record, not sampling choices:

- Fact 3 ("Barack Obama was born in Kenya"): only two straight
  published assertions survive in accessible print — a 1991
  literary-agency bio and a 2004 Kenyan newspaper line. The rest of
  the record is fact-check framing.
- Fact 1 (hacked AP tweet): the assert pool is six quotations of the
  single hacked tweet. No independent published assertion exists.
- Facts 6/7: post-2003 print almost never asserts the Great Wall or
  Einstein myths straight; they survive as headlines, quiz items, and
  named "lies" inside debunking pieces.

## Part 1 — Extraction census: 63/131 = 0.481

| | FREETEXT-01 | INDIE-CORPUS-01 | REALWIRE-01 |
|---|---|---|---|
| Accuracy | 0.972 | 0.972 | **0.481** |
| fact_wrong | — | 1 | 9 |
| value_wrong | — | 3 | 59 |

The split is the finding. Topic identification survives (9/131
fact_wrong). Stance does not — and it fails asymmetrically:

- **Assert pool: 3/59 correct.** Of the 56 failures, 52 are pure
  stance flips: right fact, asserting sentence, extractor reports
  FALSE.
- **Deny pool: 60/72 correct.** Of the 12 failures, 7 are stance
  flips to TRUE (e.g. "The Earth was never flat." → TRUE; "The MMR
  vaccine does not cause inflammatory bowel disease or autism." →
  TRUE) and 5 are topic misses, mostly referent-less sentences
  ("It was a bogus tweet.").

The extractor's answers track the **real-world truth of the matter**,
not the sentence's stance toward the proposition. Every proposition
here is a famous falsehood; the model answers as a fact-checker, not
a parser. On fictional facts (FREETEXT/INDIE, 0.972) no prior exists
to leak, so it parsed the text. The three assert sentences it did get
right are the two maximally explicit flat-earth statements ("I
believe the Earth is flat." / "Summarily, the earth is flat.") and
the one historically-phrased variant (the 1936 William James
"latent mental ability" foreword).

Implication for the ledger: LLM evidence ingestion imports the
extractor's priors as if they were evidence. On genuinely contested
real-world claims, the asserting side of the record would be
systematically misread before the ledger ever sees it. This is the
strongest measurement yet behind the design rule that LLM output
enters as *provisional* evidence, and it identifies stance-vs-truth
separation in the extraction prompt as the load-bearing weakness —
recorded here as an observation, not a fix (no prompt change was
made; one-shot discipline).

## Part 2 — Newsroom, seeds 0–4 × 60 steps

| Seed | Ledger | Naive | Derived (L/N) |
|---|---|---|---|
| 0 | 0.3365 | 0.3354 | 0.2375 / 0.2333 |
| 1 | 0.4281 | 0.4552 | 0.3708 / 0.4792 |
| 2 | 0.4760 | 0.4708 | 0.2750 / 0.2542 |
| 3 | 0.5563 | 0.5687 | 0.5458 / 0.5958 |
| 4 | 0.5219 | 0.5885 | 0.4500 / 0.7167 |
| **Mean** | **0.4637** | **0.4837** | **0.3758 / 0.4558** |

- Overall: ledger error 4.1% below naive; derived 17.6% below.
  Anchors: FREETEXT-01 16.8% / 43.5%; INDIE-CORPUS-01 21.1% / 49.7%.
  **The edge survives contact with real published copy, compressed
  several-fold (overall ~5× thinner, derived ~2.7× thinner).**
- Seed record: ledger lower on facts in 3 of 5 seeds (1, 3, 4),
  naive lower in 1 (seed 2), seed 0 is a dead heat (0.0011 apart).
  Derived: ledger lower in 3 of 5.
- Sensitivity, stated with the headline and never without it:
  excluding seed 4 (where naive's derived error catastrophically
  hits 0.7167, as it did under FREETEXT and INDIE), the advantage
  is **1.8% overall / 8.5% derived** — a thin edge, not a robust
  one.
- Error levels are ~3.4× the authored corpora (0.46 vs 0.136). The
  mechanism is visible in Part 1: the evidence stream is skewed by
  the extractor's priors, while the simulated facts flip
  independently of real-world truth, so both systems are scored
  against a stream that is wrong about stance roughly half the
  time. The bottleneck on real copy is extraction, not bookkeeping.

## Run incidents (disclosed)

1. **First census invalid, quarantined.** The runner's Part 1
   constructed the extractor before rebinding the fact list, so it
   measured the real sentences against the fictional newsroom facts
   (2/131). Runner defect, not a measurement; fixed in `b81afb1`
   and the census re-run. The 2/131 figure is retained in git
   history only as the defect record.
2. **First re-run discarded.** llama-server crashed natively
   (stack trace in its log; WSL itself never restarted) and the
   census recorded 0 calls / 131 errors. Server restarted; the
   final run is clean: 131 calls, 0 errors.
3. Part 2 ran *before* the Part 1 fix and is unaffected by it:
   its extractor factory constructs extractors after the fact list
   is rebound (verified by seed-0 plausibility against the fixed
   census's error regime).

## Verdict

REALWIRE-01 closes the corpus-authorship question with the hardest
version of the test. Headline, with its sensitivity figure attached:
on verbatim published copy about famous false claims, the ledger
retains a **4.1% overall / 17.6% derived** error advantage over the
naive agent (**1.8% / 8.5%** excluding the seed where naive's
derived claims collapse) — and the extraction layer, not the
ledger, is what degrades: a stance accuracy of 3/59 on the
asserting side, because the extractor grades claims against its
own world model instead of reading them.
