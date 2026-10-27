# Epistemic Ledger

[![CI](https://github.com/AXIOVEX/epistemic-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/AXIOVEX/epistemic-ledger/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/AXIOVEX/epistemic-ledger/graph/badge.svg)](https://codecov.io/gh/AXIOVEX/epistemic-ledger)
[![PyPI](https://img.shields.io/pypi/v/epistemic-ledger.svg)](https://pypi.org/project/epistemic-ledger/)
[![Documentation](https://readthedocs.org/projects/epistemic-ledger/badge/?version=latest)](https://epistemic-ledger.readthedocs.io/)
[![Python](https://img.shields.io/pypi/pyversions/epistemic-ledger.svg)](https://pypi.org/project/epistemic-ledger/)

> A living epistemic scoring system where every conclusion lives in an append-only database with a fluid certainty score, and new facts automatically trigger re-evaluation of the conclusions — and their dependents — that they affect, instead of any judgment ever being final.

Databases are deeply flawed: there is no built-in way to keep challenging the data, to know how true any of it is, or to update it as the evidence comes in. The epistemic ledger is an attempt to fix that — an append-only epistemic database over which an active feedback loop runs, so records are never destroyed but certainty stays fluid, and the system corrects itself, including its previously built structure.

## Status

**Implemented and validated** (v0.11.1, 2026-10-09). The framing below became a working prototype: an event-sourced, bitemporal ledger with a dependency-propagated revisit loop, learned entrenchment, Dempster-Shafer intervals, joint likelihoods, contradiction detection and resolution, governance (writer tiers, signed verdicts, escalation, named-graph authority ceilings, predicate policies), an offline LLM consolidation pass, and a hardened single-writer store with integrity verification. See [`docs/PAPER.md`](docs/PAPER.md) for the framing paper, `docs/DESIGN-*.md` for the design memos, and `docs/research/` for the raw research notes with provenance.

Measured results so far, each with its own report in `docs/`:

- **Revision value** (CONTEXT-CLEANUP-01, REPO-HISTORY-VALIDATION): the revisit loop eliminates 70.6% of naive staleness errors on dependency chains, 62.8% with joint likelihoods, 81.0% on this repository's own git history.
- **Trigger discipline** (TRIGGER-STRESS-01): epsilon 0.005 balances recall 0.96 / precision 0.72; the cutoff earns its keep.
- **Adversarial newsroom** (NEWSROOM-01, LOCAL-EXTRACTION-01): against adversarial sources the ledger eliminates 20.8% (modeled extraction) to 22.2% (real LLM extraction, local Qwen3-8B, $0) of a frozen baseline's errors — 51-61% on derived claims.
- **Free prose** (FREETEXT-01): on authored non-template text the advantage thins to 16.8% / 43.5% derived and becomes seed-dependent; the report states the sensitivity plainly.
- **Independent prose** (INDIE-CORPUS-01): on text authored by a different model family (GPT-4.1), the advantage reproduces at 21.1% / 49.7% derived with a different failure anatomy — the authorship caveat is retired.
- **Kill bars** (KILL-BARS-01): every gate threshold re-measured across all workload families; two adjusted under a pre-stated rule, one held at its definitional value on the record.
- **LLM consolidation** (CONSOLIDATION-01, LOCAL-CONSOLIDATION-01): the offline pass matches frontier-model precision/recall locally at $0 — in its thinking configuration; the no-thinking configuration fails, measurably.
- **Churn and calibration** (CHURN-01, CALIBRATION-01): conflict-normalized material churn gates at 8; a proposed agent-tempering fix was tested and *refuted* — reported as a negative.
- **Override loop** (OVERRIDE-CAL-01): v0.11.1 makes manual scores propagate through the revisit loop (they previously updated one claim and stopped); scripted-reviewer personas put the override-rate bar on a measurement for the first time (observed 0.020-0.035 vs the 0.20 bar). Human-reviewer calibration remains the honest residual.
- **Real published copy** (REALWIRE-01): on verbatim sentences from the published record, extraction accuracy collapses to 0.481 — the local extractor answers "is this true?" instead of "what does this sentence say" — while the bookkeeping edge survives, compressed (4.1% facts / 17.6% derived, vs 21.1% / 49.7% on authored prose).
- **Stance failure, diagnosed** (STANCE-01, STANCE-02): frozen diagnostic studies isolate the mechanism — proposition-level prior interference, with a dose-response over familiarity — and test the fixes: a hosted frontier model passes every bar (REALWIRE 0.977); prompt-level structure trades bias for abstention; proposition masking maps a structural ceiling on real copy.
- **Proof package** (2026-10-09): the post-freeze claims re-measured on the frozen downstream protocol. A base-model upgrade (Qwen3.5-9B, identical prompts) cuts local downstream error 0.4637 → 0.3194; structured variants (0.3073, 0.3300) do not separate from the plain baseline outside seed noise. Production default: baseline prompt on Qwen3.5-9B, structured escalation where abstention is acceptable, frontier arm as the only strong-band configuration. A supervised fastText floor (0.618 on REALWIRE stance) and a five-model fold bench accompany the result.
- **Ported into production tooling**: the measured defaults ship in the deterministic Applied Epistemic Engineering engine (`aee` 1.4.0 on PyPI — policy gates, per-source reliability, materiality review queue) and the Spec Kit AEE extension 1.2.0, with the transfer map recorded in that repository.
- **Measured, killed** (LORA-01, 2026-10-20): a LoRA adapter trained on truth-orthogonal stance data improved held-out assertion accuracy (0.903 → 0.972) but failed the frozen primary bar (+0.10 improvement required, +0.069 measured) and learned to abstain on real published copy (14/131 REALWIRE sentences), regressing REALWIRE-T. Killed as a production candidate under its predeclared criteria; the production default (Q35A) is unchanged. Full record in docs/LORA-01.md.
- **Measured, killed** (LORA-02, 2026-10-20): the successor adapter - trained with near-miss distractors against LORA-01's abstention failure and judged by headroom-based error-reduction bars - fixed every held-out assert error (0.958 to 1.000) but abstained on 30% of REALWIRE and damaged deny accuracy on real copy (REALWIRE-T deny 0.891 to 0.655). Killed under its frozen bars; across both LoRA studies, stance training on authored sentences does not transfer to real published copy. Production default (Q35A) unchanged. Full record in docs/LORA-02.md.

## Install

```bash
pip install epistemic-ledger
```

```python
from epistemic_ledger import Ledger

ledger = Ledger("my-ledger")
claim = ledger.assert_claim("the bridge design is safe", 0.60)
fact = ledger.ingest_evidence("load test passed", 0.90)["fact_id"]
ledger.add_support(claim, fact, "evidential", p_given=0.95, p_given_not=0.30)
print(ledger.get_score(claim))
```

Command line: `epistemic-ledger demo`, `epistemic-ledger verify <dir>`,
`epistemic-ledger kill-metrics <dir>`. Full documentation:
https://epistemic-ledger.readthedocs.io/

## The idea in brief

1. **Append-only records.** Conclusions are never mutated or deleted. Corrections are new records that supersede old ones — the full history of what was believed, and when, stays queryable.
2. **Fluid certainty scores.** Every conclusion carries a score that moves as evidence accumulates — today's posterior is tomorrow's prior — rather than a one-time binary verdict.
3. **Dependency-tracked revisits.** Each conclusion records *why* it is held. When a new fact arrives, the system propagates the change along the dependency graph and re-evaluates exactly the conclusions it touches, plus their dependents.
4. **A trigger discipline.** Not every new fact warrants a revisit. The system needs a principled answer to *when* — from coarse dirty-flagging up through precise invalidation to judgmental materiality thresholds.

## Research foundations

Eight threads were surveyed to frame the design (canonical references in [`docs/PAPER.md`](docs/PAPER.md)):

| # | Thread | What it gives the ledger |
|---|--------|--------------------------|
| 1 | Bitemporal data modeling | Valid time vs. transaction time; retroactive correction without mutation |
| 2 | Belief revision (AGM) | Minimal-change revision; epistemic entrenchment as the "what to give up" rule |
| 3 | Truth maintenance (JTMS/ATMS) | Justification-tracked beliefs; dependency-directed retraction |
| 4 | Event sourcing | Append-only log; state as replay; compensating events |
| 5 | Incremental recomputation | Invalidation propagation; early cutoff; DBSP's formal delta theory |
| 6 | Change-impact analysis | The trigger problem: dirty flags → precise invalidation → materiality |
| 7 | Non-binary epistemic scoring | Sequential Bayes; Jeffrey kinematics for uncertain evidence |
| 8 | LLM memory & context cleanup | Offline consolidation; RAG freshness; bitemporal knowledge graphs |

The closest existing systems to the whole: **Zep/Graphiti**-style bitemporal knowledge graphs (event time + ingestion time per edge, non-lossy retroactive correction), with TOKI (bitemporal contradiction resolution for agent memory), SodaMem (temporal graph memory with provenance and supersession edges), Engram (bi-temporal memory with invalidation and supersession chains), and MemTX (belief-commit protocol that repairs derived records when a belief is retracted) as close on other axes — none carries a certainty score revised as evidence accumulates, and none has the ledger's materiality rule for when a change warrants a revisit.

## Why this matters beyond one project

The same machinery answers a pressing LLM problem: **context cleanup**. Retrieval freshness, offline memory consolidation, and principled invalidation of stale context are exactly the ledger's operations applied to an agent's working memory. Whatever is built here generalizes.

## Repository layout

```
.
├── README.md            # This file
├── LICENSE              # MIT (code); docs/ stays all rights reserved — see NOTICE.md
├── docs/
│   ├── PAPER.md         # The framing paper
│   ├── DESIGN-01-record-schema-scoring.md  # Record schema + scoring calculus
│   ├── DESIGN-02-contradiction-resolution.md  # Entrenchment-ordered contraction
│   ├── DESIGN-03-learned-entrenchment.md   # Calibration-derived entrenchment
│   ├── DESIGN-04-ds-intervals.md           # D–S intervals: keep-or-cut verdict
│   ├── TRIGGER-STRESS-01.md  # Trigger-discipline stress test report
│   ├── CONTEXT-CLEANUP-01.md  # LLM context-cleanup experiment report
│   └── research/        # Raw research notes with provenance (2026-09-30)
│       └── BIBLIOGRAPHY.md  # Annotated bibliography: primary-source verification (2026-10-01)
├── src/epistemic_ledger/  # The package (stdlib-only Python)
├── tests/               # Test suite
├── prototype/           # Research scripts + compatibility shims
│   ├── validation/      # Measured-result harnesses (not shipped)
│   └── demo.py          # End-to-end scenario
└── .gitignore
```

## Prototype v0.1

A working implementation of Design Memo 01's §8 scope — now the shipped package under `src/epistemic_ledger/`, with the research harnesses remaining in [`prototype/`](prototype/): append-only JSONL event log, SQLite bitemporal claim table, Jeffrey-update revisit loop with early cutoff, one materiality rule, the four queries (`BELIEVED_AT` / `CHANGED` / `DEPENDS_ON` / `WHY`), and all five kill criteria instrumented from day one.

```bash
pip install -e ".[dev]"   # from the repo root
epistemic-ledger demo      # end-to-end scenario
python -m pytest           # the full test suite
```

## License

Code: MIT — see [LICENSE](LICENSE). The framing paper, design memos, and research documents under `docs/` remain all rights reserved, © 2026 Axiovex Systems, LLC — see [LICENSE-DOCS.txt](LICENSE-DOCS.txt) and [NOTICE.md](NOTICE.md).
