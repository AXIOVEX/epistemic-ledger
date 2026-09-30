# Topic 5 — Provenance, dependency tracking, incremental recomputation (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism: invalidation propagation
The universal pattern: record fine-grained dependencies (which inputs each derived value read); when an input changes, push the change forward along dependency edges, recomputing only affected nodes, and stop when outputs stabilize (quiescence / early cutoff).

1. **Incremental view maintenance (databases).** Delta rules: for a view V=Q(R), compute ΔV from ΔR instead of recomputing Q. The **counting algorithm** (Gupta–Mumick–Subrahmanian, SIGMOD 1993) stores per-tuple derivation counts — a tuple survives retraction iff count > 0; **DRed** (delete-and-rederive) handles recursive views by over-deleting then re-deriving what still has support. Higher-order IVM (**DBToaster**, Koch et al., VLDB J. 2014) maintains a hierarchy of auxiliary materialized delta views so each maintenance step is itself a cheaper query — polynomial speedups, often O(1)-amortized maintenance.
2. **DBSP** (Budiu, McSherry, Ryzhyk, Tannen, VLDB 2023): the most rigorous framework. Streams with differentiation D and integration I; the incremental version of any streaming query S is SΔ = D ∘ S ∘ I. **Z-sets** (integer-weighted relations: insert = +1, retraction = −1) unify inserts/deletes; the chain rule for the ∇ operator makes *any* relational query — joins, aggregates, nested and recursive queries — incrementalizable from a small set of primitives. ΔV = D(↑Q(I(T))).
3. **Differential Dataflow** (McSherry, Murray, Isaacs & Isard, CIDR 2013): generalizes incremental computation to partially ordered (time, iteration) timestamps, so incremental updates and fixed-point iteration compose — the basis of Materialize and DDlog; shared indexed state ("arrangements").
4. **Provenance semirings** (Green, Karvounarakis & Tannen, PODS 2007): relational evaluation parameterized by a commutative semiring uniformly captures bag semantics, counting, and provenance; Z-sets are this construction over ℤ — the algebraic ancestor of DBSP. Provenance tells you *which* input tuples contribute to each output (why-provenance for the invalidation question).
5. **Build systems (Bazel-style):** explicit, hermetic dependency graph. Content-addressed **action cache**: hash(inputs + command + environment) → outputs (a "constructive trace," shareable across machines as remote cache). **Early cutoff**: if a re-executed action produces a byte-identical output, downstream rebuilds are skipped — value-based invalidation that stops cascades. `rdeps(//..., //target)` answers "what does this change invalidate."
6. **Self-adjusting computation** (Acar, CMU PhD thesis CMU-CS-05-129, 2005): the program records a **dynamic dependence graph** while running on initial data; a **change-propagation algorithm** re-executes only the affected subcomputations when inputs (or internal decisions) change. **Trace memoization** reuses sub-traces: a recursive sum over [1..5] extended to [99,1..5] reuses the cached trace for the unchanged tail — O(log n)/O(1) vs O(n) for value memoization. Consistency theorem: reuse is sound. Cost depends on **trace stability**.
7. **Demand-driven / lazy:** magic sets / SIPS (pull only query-relevant data); salsa (rustc) — **verifying traces** (persist hash of a key's value + hashes of dependencies' values at that time); recomputation answered by comparing fingerprints; TypeScript `.tsbuildinfo` signatures. Pull avoids push's retained-state cost.

## Canonical references
1. Gupta & Mumick, "Maintenance of Materialized Views: Problems, Techniques, and Applications," IEEE Data Eng. Bulletin 18(2), 1995 — the survey (immediate vs deferred maintenance, self-maintainability).
2. Gupta, Mumick & Subrahmanian, "Maintaining Views Incrementally," SIGMOD 1993 — counting algorithm, DRed.
3. Koch et al., "DBToaster: Higher-order Delta Processing for Dynamic, Frequently Fresh Views," VLDB J. 23(2), 2014.
4. Budiu, McSherry, Ryzhyk & Tannen, "DBSP: Automatic Incremental View Maintenance for Rich Query Languages," VLDB 2023.
5. McSherry, Murray, Isaacs & Isard, "Differential Dataflow," CIDR 2013.
6. Green, Karvounarakis & Tannen, "Provenance Semirings," PODS 2007.
7. Acar, "Self-Adjusting Computation," CMU-CS-05-129, PhD thesis, 2005 (committee: Blelloch, Harper, Sleator, Peyton Jones, Tarjan).

## Practical limitations
- **Retained state is the cost center:** push systems (differential dataflow, DBSP) retain full integrated input at stateful operators to be ready for any delta — in direct tension with partial replicas.
- Higher-order IVM can demand O(N²) auxiliary space for some queries.
- **Non-invertible aggregates** (MIN/MAX): a retraction can un-mask a previous extremum → need auxiliary structures (heaps) or reformulation; invertible ones (SUM/COUNT) retract in O(1).
- SAC: adversarial input changes can make traces unstable → change propagation degrades to full recomputation; memoization tables cost memory.
- Dynamic/unknown dependencies defeat precision: Make's mtime comparison and Excel's INDIRECT over-approximate (mark dirty "if the formula statically refers to a dirty cell, or uses a function whose dependencies cannot be guessed"). Deep/flat hash traces (Turborepo/Nx style) require determinism and sacrifice early cutoff.
- Early cutoff / verifying traces only work if recomputation is deterministic (hashes must be stable).

## Sources
- https://github.com/ampersandtarski/ampersand/blob/HEAD/memorybank/incremental-evaluation/ecosystem-and-video.md (annotated literature: Gupta & Mumick 1995; Gupta/Mumick/Subrahmanian 1993 counting+DRed; Green/Karvounarakis/Tannen 2007; Koch 2010 ring; DBToaster 2014; McSherry et al. CIDR 2013)
- https://github.com/mono424/sp00ky/blob/HEAD/docs/dbsp-deep-dive.md (DBSP VLDB 2023, Budiu/McSherry team; "any relational query can be incrementalized")
- https://www.researchgate.net/publication/359647360_DBSP_Automatic_Incremental_View_Maintenance_for_Rich_Query_Languages (DBSP paper: SΔ = D ∘ S ∘ I; ΔV = D(↑Q(I(T))))
- https://github.com/adamartin18010/analysisdataflow/blob/HEAD/en/dbsp-differential-dataflow.md (DBSP↔DD relationship; ΔV = Q̂(ΔR); Materialize engine)
- https://github.com/samyama-ai/dbms_research/blob/HEAD/topics/18-streaming-queries/streaming-retraction-ivm.md (Z-relations, delta rules, DRed, differential dataflow lattice timestamps, invertible vs non-invertible aggregates)
- https://www.cs.cmu.edu/~rwh/students/acar.pdf (Acar PhD thesis 2005: dynamic dependence graphs, change propagation, memoization, trace stability)
- https://github.com/bigmistqke/pulse/blob/HEAD/docs/async/deep-dives/self-adjusting-computation.md (value vs trace memoization worked example; consistency theorem)
- https://github.com/parnmanas/ai-workflow-board/blob/HEAD/docs/ontology-graph/research-incremental.md (verifying traces: salsa fingerprints, rustc DefPathHash, tsbuildinfo; constructive traces = Bazel remote cache; deep traces; Excel/Make over-approximation)
- https://dev.to/jakeherringbone/bazel-what-you-give-what-you-get-5a91 (Bazel early cutoff: identical result → no further work, avoids cascading rebuilds)
