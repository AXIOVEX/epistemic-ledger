# Topic 6 — Change-impact analysis / the trigger problem (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism: deciding WHEN a change warrants recomputation
Three complementary mechanisms, from coarsest to most precise:

1. **Dirty-flagging (coarse, sound, imprecise).** Mark changed inputs dirty; propagate the dirty bit along static dependency edges; recompute everything downstream. Examples: spreadsheet recalculation (Excel marks a cell dirty if a formula statically refers to a dirty cell); Make's mtime comparison. **Over-approximates by construction** — Excel is *forced* to over-invalidate for functions like INDIRECT whose dependencies cannot be guessed. Without early cutoff this causes whole-spine cascading rebuilds.
2. **Precise invalidation (dependency graph + value comparison).** Recompute only when an input's *value* actually changed, not merely when it was touched: Bazel's **early cutoff** (rebuilt output byte-identical → downstream skipped); salsa/rustc **verifying traces** (persist hash of a key's value plus the hashes its dependencies had; recompute iff fingerprints differ); TypeScript `.tsbuildinfo` signatures. This is the practical answer to "does this new fact affect that conclusion" at the value level.
3. **Materiality thresholds & sensitivity (judgmental/quantitative).** Even a real change may not warrant action:
   - **Sensitivity analysis:** how much does the output move per unit input change (numerical gradients, perturbation bounds) — decides whether a change is *immaterial* to the conclusion.
   - **Domain materiality rules:** accounting/impairment practice — ASC 350 requires interim goodwill impairment testing on **triggering events** when there is >50% probability a reporting unit is impaired (deterioration in macro conditions, stock decline, cash-flow loss, adverse regulatory change, etc.). Materiality thresholds in practice are tuned by output ("aim for 8–15 flagged lines a month; under eight the filter is eating real movement; over fifteen you won't finish").
   - **Value of information:** expand/recompute only when a different answer could change the final outcome (used as a stopping rule for decomposition in the docket outcome-formalism note).
   - **Lazy vs eager:** dirty-flag now, recompute on demand (pgcache: invalidation is an in-memory state flip Fresh→Pending; rebuild triggered lazily by a cache hit).

## Formal treatment of "does this fact affect that conclusion?"
- **DBSP** gives the formal account: the incrementalized query SΔ computes *exactly* the change induced by an input delta; "this fact does not affect that conclusion" ⟺ the propagated delta is empty (Δ = 0 through the delta rules). Retraction = negative weight, so a fact and its retraction provably cancel.
- **Provenance semirings** (Green et al.): the provenance annotation of an output records precisely which input tuples contributed — the formal "why does this conclusion depend on that fact."
- **Self-maintainability** (Gupta & Mumick): whether a view can be maintained from the delta alone, without consulting base tables — the formal boundary of "the change carries enough information."
- No single off-the-shelf formalism covers the *judgmental* side (materiality); that remains domain thresholds + sensitivity analysis.

## Practical limitations
- Precise invalidation needs exact dependency information, which is expensive to maintain and defeated by dynamic dependencies (INdirect-style).
- Early cutoff/verifying traces require deterministic recomputation (stable hashes).
- Materiality thresholds are domain judgments that must be tuned empirically and re-tuned as scale changes; percentage-based thresholds misbehave near zero.
- Sensitivity analysis needs a continuous/differentiable model or a perturbation harness; not available for arbitrary symbolic derivations.
- Dirty-flagging is simple and sound but over-invalidates; precise invalidation is efficient but complex to implement correctly (getting delta rules wrong = silent divergence from truth, per the DBSP deep-dive note).

## Sources
- https://github.com/parnmanas/ai-workflow-board/blob/HEAD/docs/ontology-graph/research-incremental.md (Excel/Make dirty-flag over-approximation; INDIRECT; verifying traces — salsa, rustc, tsbuildinfo; constructive traces; determinism requirement)
- https://github.com/pgcache/pgcache/blob/HEAD/ADR/ADR-031-materialized-query-results.md (invalidation as in-memory state flip Fresh→Pending; lazy coordinator-driven rebuilds)
- https://dev.to/jakeherringbone/bazel-what-you-give-what-you-get-5a91 (Bazel early cutoff stops cascading rebuilds)
- https://www.valuationresearch.com/insights/triggering-event-impairment-testing/ (ASC 350 triggering events: >50% probability threshold; market turbulence factors)
- https://www.inkle.ai/blog/materiality-threshold-variance-review (tuning materiality thresholds by output: 8–15 flagged lines/month; percentage bars misbehave near zero)
- https://github.com/mono424/sp00ky/blob/HEAD/docs/dbsp-deep-dive.md (delta rules must be exactly right or views silently diverge — the precision requirement)
- https://github.com/novusedge/docket/blob/HEAD/docs/outcome-formalism.md (value-of-information stopping rule: expand only when a different answer can change the final outcome)
