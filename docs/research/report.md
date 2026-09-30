# Living Epistemic Ledger — Research Report

**Mission:** inform the design of a "living epistemic ledger": an append-only record system where past conclusions carry fluid certainty scores that get revised as new facts arrive, with automatic detection of which dependent conclusions must be revisited.

**Research date:** 2026-09-30. **Confidence basis:** all findings below are `index`-level (web search results and their page text), cross-checked across 2+ independent sources per topic where possible. Nothing was `verified live` in an interactive browser session; canonical paper facts (authors, venues, years) are stable bibliographic facts reported consistently across sources.

## Summary

Eight research threads converge on a coherent design vocabulary for the ledger:

| # | Topic | Core mechanism for the ledger |
|---|-------|-------------------------------|
| 1 | Bitemporal modeling | Separate **valid time** (when a claim held in the world) from **transaction time** (when the ledger learned it); retroactive corrections are new rows with past valid time + current transaction time — nothing is ever mutated |
| 2 | AGM belief revision | Revision = add the new fact, retract the *least-entrenched* prior beliefs needed for consistency (**Levi identity**); epistemic entrenchment is the principled "what to give up" rule |
| 3 | Truth maintenance | **Justifications as edges**: JTMS = one consistent labeling with dependency-directed backtracking; ATMS = many contexts via assumption-set labels + nogoods. Labels can blow up **exponentially** — the central scaling warning |
| 4 | Event sourcing | Append-only log of immutable events; state = replay; corrections = **compensating events**, never rewrites (except controlled, audited stream migration) |
| 5 | Incremental recomputation | **Invalidation propagation**: push deltas along the dependency graph, recompute only affected nodes, stop on **early cutoff** (output unchanged ⇒ halt cascade). DBSP gives the formal theory (SΔ = D ∘ S ∘ I) |
| 6 | Trigger problem | Three layers: dirty-flagging (coarse, over-invalidates) → precise value-based invalidation (Bazel early cutoff, verifying traces) → materiality/sensitivity thresholds. Formal "does this affect that": **Δ = ∅ through the delta rules** |
| 7 | Epistemic scoring | **Sequential Bayesian updating** (today's posterior = tomorrow's prior); **Jeffrey conditionalization** for uncertain evidence; Dempster–Shafer belief/plausibility intervals when ignorance must be represented explicitly |
| 8 | LLM memory | Hierarchical paging (Letta), **offline consolidation** beats write-time extraction (sleep-time compute), RAG freshness via content-hash change detection + versioned indexes; bitemporal knowledge graphs (Graphiti) already combine 1+8 |

**Strongest cross-cutting findings:**
- The "never mutate, supersede with bitemporal rows" discipline (topic 1) + "compensating events" (topic 4) + "dependency-directed retraction" (topic 3) are three expressions of the same append-only correction pattern.
- The formal answer to "which conclusions must be revisited" already exists twice: **ATMS-style justification/environments tracking** (symbolic) and **DBSP/differential-dataflow delta propagation** (dataflow). Both have known exponential/state blowup failure modes.
- For fluid certainty scores, **sequential Bayes with Jeffrey kinematics** is the canonical graded mechanism; Dempster–Shafer adds explicit ignorance representation at the cost of exponential mass-function blowup.
- State of the art for LLM context accuracy is *not* a formal TMS (none runs at LLM-KG scale in production): it is retrieval-side freshness + offline consolidation. Graphiti's bitemporal edges (event time + ingestion time) are the closest existing system to the ledger's goal.

---

## 1. Bitemporal Data Modeling (valid time vs. transaction time)

**Core mechanism.** Every fact is tagged with two independent intervals (sources: ADR-014 temporal prior art, index, 2026-09-30; bmf-tech bitemporal design guide, index, 2026-09-30):
- **Valid time (VT):** the period during which the fact is true in the modeled reality.
- **Transaction time (TT):** the period during which the fact was stored in the database.
- A bitemporal tuple is `(proposition, VT_start, VT_end, TT_start, TT_end)`. This enables four query modes: current knowledge of current facts (`VT_end = ∞ AND TT_end = ∞`); historical knowledge (`VT at T₁ AND TT at T₂`); **retroactive corrections** (insert with past VT but current TT); rollback queries ("what did the system believe at TT = T₂?").

**Retroactive corrections.** The canonical representation is: **never mutate in place** — close the old record's transaction-time interval at correction time and insert a new record carrying the corrected valid time with the current transaction time (sources: nodedb bitemporal docs with `AS OF VALID TIME` / `AS OF SYSTEM TIME` examples, index, 2026-09-30; ekgardt llm-wiki bitemporal-claims research note, index, 2026-09-30). A query asked with an earlier `known_at`/TT still returns the pre-correction answer, because the correction was not known yet. Original and corrected data remain visible simultaneously — the audit property the ledger needs. Snodgrass's motivating use case for full bitemporality was precisely retroactive correction of recorded history (ADR-014, index, 2026-09-30).

**Canonical references.**
1. Snodgrass & Ahn, "A Taxonomy of Time in Databases," SIGMOD 1985 — the VT/TT taxonomy (cited in ADR-014, index, 2026-09-30).
2. Jensen et al., "The Consensus Glossary of Temporal Database Concepts," LNCS 1399 — the standard vocabulary (cited in ADR-014, index, 2026-09-30).
3. Allen, "Maintaining Knowledge about Temporal Intervals," Communications of the ACM 26:832–843, 1983 — the 13-relation interval algebra for temporal queries (cited in ADR-014, index, 2026-09-30).
4. TSQL2 (Snodgrass ed., 1995), later standardized as **SQL:2011** application-time (valid) and system-time (transaction) tables with `PERIOD FOR` and `AS OF` queries (ADR-014; nodedb docs, index, 2026-09-30). Production systems: **XTDB** (snapshot/diff operators), Datomic, SQL Server temporal tables, MariaDB.

**Practical notes / limitations.**
- Use half-open intervals `[from, to)` per the SQL:2011 convention: ending one interval and starting its successor at the same instant then yields exactly one current row (ADR-014, index, 2026-09-30).
- Full bitemporality only pays off if the past can be corrected; systems that only query the past can use "bitemporal-lite" (valid-time state table + transaction-time audit) — a recognized, defensible point on the spectrum (ADR-014, index, 2026-09-30).
- Querying two axes is conceptually and operationally harder and more expensive to index; engine support is not universal, so many teams hand-roll it.

## 2. Belief Revision Theory (AGM paradigm)

**Core mechanism.** Belief set K = a deductively closed set of sentences. Three operations (sources: Huber, "Belief Revision I: The AGM Theory," Philosophy Compass 8/7 (2013), index, 2026-09-30; dent8 belief-revision doc, index, 2026-09-30):
- **Expansion** K+α = Cn(K ∪ {α}): add α, remove nothing.
- **Contraction** K−α: remove α (unless it is a tautology), add nothing.
- **Revision** K∗α: add α while removing whatever is necessary to restore consistency.
- **Levi identity** (Levi 1977): K∗α = (K−¬α)+α — revision reduces to *contraction by the negation, then expansion*. **Harper identity** (Harper 1976) gives the converse.

**Minimal change / informational economy.** Give up as little of K as possible, formalized two ways:
- *Partial-meet contraction:* intersect a selection of the maximal subsets of K not implying α.
- *Epistemic entrenchment* (Gärdenfors–Makinson): a preference ordering over beliefs (transitivity, dominance, conjunctiveness, minimality, maximality). On conflict, surrender the **least entrenched** belief that restores coherence — core beliefs survive, peripheral ones go (Huber 2013; dent8 doc, index, 2026-09-30).

**How a rational agent incorporates a contradicting new fact:** revision — accept the new sentence (Success postulate) and retract the minimal, least-entrenched prior commitments needed for consistency. If the new fact is already consistent with K, revision collapses to plain expansion (Vacuity/Preservation). The revision postulates (∗1–∗8: Closure, Success, Inclusion, Preservation, Consistency, Congruence, Conjunction 1 & 2) and contraction postulates (−1–−8: Closure, Success, Inclusion, Vacuity, Extensionality, the disputed **Recovery** K ⊆ (K−p)+p, Conjunction 1 & 2) pin down "rational" change; Katsuno & Mendelzon (1991) rephrased them for finite propositional bases (R1–R6) with a representation theorem via total pre-orders over worlds (Huber 2013; Springer JBCS article on iteration of expansion, index, 2026-09-30).

**Canonical references.**
1. Alchourrón, Gärdenfors & Makinson, "On the Logic of Theory Change: Partial Meet Contraction and Revision," J. Symbolic Logic 50(2), **1985** — the AGM paper.
2. Gärdenfors, *Knowledge in Flux: Modeling the Dynamics of Epistemic States*, MIT Press, **1988** — book-length treatment including epistemic entrenchment.
3. Levi (1977) — Levi identity; Harper (1976) — Harper identity.
4. Katsuno & Mendelzon, "Propositional Knowledge Base Revision and Minimal Change," **1991**.
5. Hansson, *A Textbook of Belief Dynamics* (1999) — **belief-base** revision (finite, syntactic, non-closed sets; derived beliefs recomputed, not stored; **Recovery fails** for bases) and **kernel contraction** — the variant that matches implemented systems rather than idealized closed sets (dent8 doc, index, 2026-09-30).

**Practical notes / limitations.**
- **Logical omniscience:** belief sets are deductively closed — no real agent computes all consequences; belief *bases* are the implementable counterpart.
- The Recovery postulate is famously disputed and fails for bases.
- AGM is **episodic**: "I had K; now I have K∗φ" — no notion of deliberating between alternatives or partial/committed revision (arisbe intellectual-history doc, index, 2026-09-30).
- Computational cost: repairing an inconsistent ontology is NP-hard or worse even in lightweight description logics; contraction is uncomputable outside narrow logic classes (nrdxp/predicate "where-correction-ends" doc, index, 2026-09-30).
- Gärdenfors' own triviality result: pairing revision with conditional reasoning collapses into inconsistency when both are made precise (same source).
- Iterated revision is underdetermined by the core postulates; frontier LLMs measurably violate AGM rationality postulates under iterated belief revision (AGM-Bench / Belief-R, per the 2026 davidamitchell truth-maintenance survey, index, 2026-09-30).

## 3. Truth Maintenance Systems (JTMS, ATMS)

**Core mechanism.** Nodes = beliefs, each carrying **justifications** (antecedent lists with IN/OUT conditions — a conclusion may depend on the *absence* of another belief, i.e., non-monotonic reasoning) (sources: aitopics classic Doyle abstract; Wray thesis excerpt on TMS usage, index, 2026-09-30):
- **JTMS — Doyle, 1979:** maintains **one** consistent context. Nodes labeled IN (believed) / OUT. When a premise changes or a contradiction is derived, labels re-propagate; **dependency-directed backtracking** traces the justification graph from the contradiction to the culprit assumption(s) and retracts exactly those, rather than backtracking chronologically. Retracting a premise automatically retracts everything that rested on it — unless an alternative justification survives.
- **ATMS — de Kleer, 1986:** maintains **many** contexts simultaneously. Each datum is labeled with the **minimal assumption-sets (environments)** under which it holds; **nogoods** record assumption-sets known to be inconsistent. Derivations are never retracted — the problem solver just selects a consistent environment. Switching world-views is cheap; comparing alternatives is the ATMS's strength (e.g., elaborating CMOS vs. gallium-arsenide designs in parallel). Assumption-based dependency-directed backtracking (ADDB); "focusing" strategies (focus environments, implied-by consumers, contradiction consumers) keep it from exploring irrelevant contexts (de Kleer, "Focusing the ATMS," 1988, index, 2026-09-30).

**Canonical references.**
1. Doyle, "A Truth Maintenance System," Artificial Intelligence 12(3), **1979** — JTMS.
2. de Kleer, "An Assumption-Based TMS," Artificial Intelligence 28(1), **1986** — ATMS.
3. de Kleer & Williams, "Back to Backtracking: Controlling the ATMS," AAAI **1986**.
4. de Kleer, "Focusing the ATMS," **1988** — the implied-by strategy for infinite domains.
5. Forbus & de Kleer, *Building Problem Solvers*, MIT Press, **1993** — textbook treatment.

**Practical notes / limitations (scaling limits).**
- **ATMS label blowup:** label sets can grow **exponentially in the number of assumptions/database literals** (the "parity problem"). UBC TR-88-11 ("The Computational Complexity of Assumption-Based Truth Maintenance Systems," index, 2026-09-30): de Kleer's incremental-generation fix stops generating all solutions at once, but "there is no way to stop the generation of the full (exponential) label set." The **problem of encoding** — efficiency depends entirely on how the problem solver encodes assumptions/clauses/consumers — confronts most ATMS users and is barely discussed in the literature (same source).
- **JTMS:** non-monotonic justification cycles can cause thrashing/relabeling loops; one-context maintenance means a wrong early choice forces expensive backtracking; both systems assume hand-encoded propositional justifications.
- Naive complete dependency-tracking is exponential in the number of retractions absorbed (justification structure grows with history; every retraction walks it) (nrdxp/predicate doc, index, 2026-09-30).
- **No production system runs a formal classical TMS at LLM–knowledge-graph scale** (2026 survey, davidamitchell research notes, index, 2026-09-30). Engineered substitutes: detect-then-resolve pipelines (CRDL), dual-memory routing (WISE).
- The durable pattern for the ledger: track *why* each belief is held; propagate retraction through the support relation; retain a claim while one complete justification set survives; remember known-bad configurations in a nogood database (docket outcome-formalism doc; jmccardle/tau brief, index, 2026-09-30). CDCL SAT solvers are the industrial heir of the nogood idea.

## 4. Event Sourcing and Append-Only Logs

**Core mechanism.** Every state change is stored as an **immutable event** (a fact about what happened) in an **append-only log**. Never update, never delete. Current state is **derived by replay** (state = left fold over the event stream); read models/projections/materialized views are built by consuming events and can be regenerated at any time (sources: Microsoft Azure Architecture Center "Event Sourcing pattern," index, 2026-09-30; DevX synthesis of Fowler/Young/Richardson, index, 2026-09-30).

**Retroactive correction.** The doctrine: "you can't change the past, but you can replay it" (Greg Young). Errors are corrected by appending **compensating events** (accounting-style reversals) — the reversal itself becomes part of the auditable record; Microsoft's pattern doc notes this "can provide a history of reversed changes" that a current-state-only model cannot. Exceptional redaction/repair (legal/operational necessity) uses a **controlled, auditable stream-rewrite / version migration**, after which every dependent projection must be rebuilt (robsonkades event-sourcing skill doc, index, 2026-09-30). Related bitemporal practice: corrections preserve the *original* valid time and carry the reason (peegeeq bitemporal guide, index, 2026-09-30).

**Engineering rules** (itohnobue/orchestrator-opencode event-sourcing architect doc; robsonkades skill doc, index, 2026-09-30): events carry full payload (never rely on current state); past-tense domain names (`OrderCreated`, not "Updated"); validate commands *before* append; optimistic concurrency via expected-version checks; idempotency via command IDs in metadata (version check ≠ idempotency); snapshotting for long streams (a snapshot is stale the moment written — always load snapshot + subsequent events); transactional outbox for reliable publishing. Commonly combined with **CQRS** (independent scaling of append-only ingestion and query-optimized projections).

**Canonical references.**
1. Greg Young — popularized the pattern ("events represent facts, which you never edit").
2. Fowler, "Event Sourcing," martinfowler.com, **2005**.
3. Microsoft Azure Architecture Center, "Event Sourcing pattern."
4. Chris Richardson — event sourcing for workflows with many transitions and strong invariants.

**Practical notes / limitations.**
- Streams grow without bound → snapshots, stream closure on business boundaries, or redesign (robsonkades skill doc, index, 2026-09-30).
- Schema evolution: old events must remain interpretable (event versioning/upcasting); "replay must not reapply today's command rules to yesterday's accepted decisions."
- Projections are eventually consistent; a wrongly recorded event is permanent (compensated but visible) — the audit trail is a feature until it is a liability (privacy/redaction vs. immutability).
- Append-only storage alone is not tamper-evidence; concurrency conflicts must be surfaced, not blind-retried.

## 5. Provenance, Dependency Tracking, and Incremental Recomputation

**Core mechanism: invalidation propagation.** Record fine-grained dependencies (which inputs each derived value read); when an input changes, push the change forward along dependency edges, recompute only affected nodes, and stop when outputs stabilize (quiescence / **early cutoff**).

- **Incremental view maintenance (databases).** Delta rules: compute ΔV from ΔR instead of recomputing the query. The **counting algorithm** (Gupta–Mumick–Subrahmanian, SIGMOD 1993) stores per-tuple derivation counts — a tuple survives retraction iff count > 0; **DRed** (delete-and-rederive) handles recursive views by over-deleting then re-deriving what still has support. **Higher-order IVM** (**DBToaster**, Koch et al., VLDB J. 2014) maintains a hierarchy of auxiliary materialized delta views so each maintenance step is itself a cheaper query — polynomial speedups, often O(1)-amortized (ampersandtarski annotated literature, index, 2026-09-30).
- **DBSP** (Budiu, McSherry, Ryzhyk & Tannen, VLDB **2023**): the most rigorous framework. Streams with differentiation D and integration I; the incremental version of any streaming query S is **SΔ = D ∘ S ∘ I**. **Z-sets** (integer-weighted relations: insert = +1, retraction = −1) unify inserts and deletes; the chain rule for the ∇ operator makes *any* relational query — joins, aggregates, nested and recursive queries — incrementalizable from a small set of primitives: ΔV = D(↑Q(I(T))) (ResearchGate DBSP paper page; sp00ky DBSP deep-dive, index, 2026-09-30).
- **Differential Dataflow** (McSherry, Murray, Isaacs & Isard, CIDR **2013**): generalizes incremental computation to partially ordered (time, iteration) timestamps so incremental updates and fixed-point iteration compose — the basis of Materialize and DDlog; shared indexed state ("arrangements") (ampersandtarski literature notes, index, 2026-09-30).
- **Provenance semirings** (Green, Karvounarakis & Tannen, PODS **2007**): relational evaluation parameterized by a commutative semiring uniformly captures bag semantics, counting, and provenance; Z-sets are this construction over ℤ — the algebraic ancestor of DBSP. Provenance answers *which* input tuples contribute to each output: the formal "why" behind invalidation.
- **Build systems (Bazel-style):** explicit, hermetic dependency graph; content-addressed **action cache** (hash of inputs + command + environment → outputs — a shareable "constructive trace" via remote cache); **early cutoff**: if a re-executed action produces a byte-identical output, downstream rebuilds are skipped — value-based invalidation that halts cascades; `rdeps(//..., //target)` answers "what does this change invalidate" (dev.to Bazel explainer; parnmanas incremental-research doc, index, 2026-09-30).
- **Self-adjusting computation** (Acar, CMU PhD thesis **CMU-CS-05-129, 2005**): the program records a **dynamic dependence graph** while running on initial data; a **change-propagation algorithm** re-executes only affected subcomputations when inputs change. **Trace memoization** reuses sub-traces: extending a recursive sum from [1..5] to [99,1..5] reuses the cached trace for the unchanged tail — O(log n)/O(1) vs O(n) for value memoization; a consistency theorem guarantees reuse is sound; cost depends on **trace stability** (Acar thesis PDF; bigmistqke/pulse SAC deep-dive, index, 2026-09-30).
- **Demand-driven / lazy:** magic sets / SIPS (pull only query-relevant data); salsa (rustc) **verifying traces** — persist the hash of a key's value plus the hashes its dependencies had; recompute iff fingerprints differ; TypeScript `.tsbuildinfo` signatures. Pull avoids push's retained-state cost (dialog-db incremental-subscriptions note; parnmanas doc, index, 2026-09-30).

**Canonical references.**
1. Gupta & Mumick, "Maintenance of Materialized Views: Problems, Techniques, and Applications," IEEE Data Eng. Bulletin 18(2), **1995** — the survey (immediate vs deferred maintenance, self-maintainability).
2. Gupta, Mumick & Subrahmanian, "Maintaining Views Incrementally," SIGMOD **1993** — counting algorithm, DRed.
3. Koch et al., "DBToaster: Higher-order Delta Processing for Dynamic, Frequently Fresh Views," VLDB J. 23(2), **2014**.
4. Budiu, McSherry, Ryzhyk & Tannen, "DBSP: Automatic Incremental View Maintenance for Rich Query Languages," VLDB **2023**.
5. McSherry, Murray, Isaacs & Isard, "Differential Dataflow," CIDR **2013**.
6. Green, Karvounarakis & Tannen, "Provenance Semirings," PODS **2007**.
7. Acar, "Self-Adjusting Computation," CMU-CS-05-129, PhD thesis, **2005** (committee: Blelloch, Harper, Sleator, Peyton Jones, Tarjan).

**Practical notes / limitations.**
- **Retained state is the cost center:** push systems (differential dataflow, DBSP) retain full integrated input at stateful operators to be ready for any delta — in direct tension with partial replicas (dialog-db note, index, 2026-09-30).
- Higher-order IVM can demand O(N²) auxiliary space for some queries (Berkeley CS294 IVM lecture slides, index, 2026-09-30).
- **Non-invertible aggregates** (MIN/MAX): a retraction can un-mask a previous extremum → need auxiliary structures (heaps) or reformulation; invertible ones (SUM/COUNT) retract in O(1) (samyama-ai streaming-retraction IVM note, index, 2026-09-30).
- SAC: adversarial input changes make traces unstable → change propagation degrades to full recomputation; memoization tables cost memory.
- Dynamic/unknown dependencies defeat precision: Make's mtime comparison and Excel's INDIRECT over-approximate; deep flat hash traces (Turborepo/Nx style) require determinism and sacrifice early cutoff (parnmanas doc, index, 2026-09-30).
- Getting delta rules wrong means views **silently diverge** from truth — precision is a correctness requirement, not an optimization (sp00ky DBSP deep-dive, index, 2026-09-30).

## 6. Change-Impact Analysis / The Trigger Problem

**Core mechanism: deciding WHEN a change warrants recomputation.** Three complementary layers, coarsest to most precise:

1. **Dirty-flagging (coarse, sound, imprecise).** Mark changed inputs dirty; propagate the dirty bit along static dependency edges; recompute everything downstream. Examples: spreadsheet recalculation (a cell is dirty if its formula statically refers to a dirty cell); Make's mtime comparison. **Over-approximates by construction** — Excel is *forced* to over-invalidate for functions like `INDIRECT` whose dependencies cannot be guessed (parnmanas incremental-research doc, index, 2026-09-30). Without early cutoff this causes whole-spine cascading rebuilds.
2. **Precise invalidation (dependency graph + value comparison).** Recompute only when an input's *value* actually changed, not merely when it was touched: Bazel's **early cutoff** (rebuilt output byte-identical → downstream skipped); salsa/rustc **verifying traces** (persist hash of a key's value plus the hashes its dependencies had at that time; recompute iff fingerprints differ); TypeScript `.tsbuildinfo` signatures (parnmanas doc; dev.to Bazel explainer, index, 2026-09-30).
3. **Materiality thresholds & sensitivity (judgmental/quantitative).** Even a real change may not warrant action:
   - **Sensitivity analysis:** how much the output moves per unit input change (gradients, perturbation bounds) — decides whether a change is *immaterial* to the conclusion.
   - **Domain materiality rules:** ASC 350 requires interim goodwill impairment testing on **triggering events** when there is >50% probability a reporting unit is impaired — deterioration in macro conditions, stock/market-cap decline, operating or cash-flow losses, revenue expectations well below forecast, adverse legal/regulatory change, production slowdowns, supply-chain disruption, demand decline (Valuation Research Corp briefing, index, 2026-09-30). A real-world, legally operationalized "this change warrants recomputation" rule.
   - **Threshold tuning is empirical:** "tune by output, not by argument" — aim for 8–15 flagged items per review cycle; under eight the filter is eating real movement; over fifteen the review won't finish; percentage thresholds misbehave near zero (inkle.ai materiality-threshold guide, index, 2026-09-30).
   - **Value of information:** expand/recompute only when a different answer could change the final outcome — used as a stopping rule for decomposition (docket outcome-formalism doc, index, 2026-09-30).
   - **Lazy vs eager:** dirty-flag now, recompute on demand (pgcache ADR-031: invalidation is an in-memory state flip Fresh→Pending; rebuilds triggered lazily by a cache hit, index, 2026-09-30).

**Formal treatment of "this new fact does/does not affect that conclusion."**
- **DBSP** gives the formal account: the incrementalized query SΔ computes *exactly* the change induced by an input delta — "this fact does not affect that conclusion" ⟺ the propagated delta is empty (Δ = 0 through the delta rules). Retraction = negative weight, so a fact and its retraction provably cancel (DBSP paper page; sp00ky deep-dive, index, 2026-09-30).
- **Provenance semirings** (Green et al., PODS 2007): each output's provenance annotation records precisely which input tuples contributed — the formal "why does this conclusion depend on that fact."
- **Self-maintainability** (Gupta & Mumick 1995): whether a view can be maintained from the delta alone without consulting base tables — the formal boundary of "the change carries enough information."
- No single off-the-shelf formalism covers the *judgmental* side (materiality); that remains domain thresholds + sensitivity analysis.

**Practical notes / limitations.**
- Precise invalidation needs exact dependency information — expensive to maintain, defeated by dynamic dependencies.
- Early cutoff/verifying traces require deterministic recomputation (stable hashes).
- Materiality thresholds are domain judgments needing empirical tuning and re-tuning as scale changes.
- Sensitivity analysis needs a continuous/differentiable model or a perturbation harness; unavailable for arbitrary symbolic derivations.
- Dirty-flagging is simple and sound but over-invalidates; precise invalidation is efficient but complex — and getting delta rules wrong yields silent divergence.

## 7. Non-Binary Epistemic Scoring

**Core mechanism.**
- **Credences as probabilities (subjective Bayesianism):** rational degree of belief = a number in [0,1] obeying the probability axioms (de Finetti 1937; Savage 1954; representation theorems of Koopman/Savage/Hawthorne: a qualitative "at least as plausible" relation satisfying axioms is uniquely representable by a probability function — SEP Inductive Logic supplement, index, 2026-09-30).
- **Updating:** Bayes' rule P(H|E) = P(E|H)·P(H)/P(E). Sequential structure: **today's posterior is tomorrow's prior**; with conditionally independent evidence, update order doesn't matter; accumulating evidence drives belief toward 0 or 1 (consistency/convergence results) (fleetingthoughts Bayesianism notes; cyberia-to Bayes theorem note, index, 2026-09-30). Norms: structural (be probabilities), evidential (calibrate to known chances; defer to experts absent better evidence), equivocation (indifference without evidence) — BJPS "A Bayesian Account of Establishing" (index, 2026-09-30).
- **Uncertain evidence — Jeffrey conditionalization / probability kinematics** (Jeffrey, *The Logic of Decision*): when evidence shifts P(B) without making B certain, P_new(A) = P_old(A|B)·P_new(B) + P_old(A|¬B)·P_new(¬B). "It's probabilities all the way down" — rejects the demand for certain foundations; cf. **Cromwell's rule** (never assign 0/1 to anything but logical truths, or no evidence can move you). Alternatives: Jaynes' maximum-entropy updating; Skyrms' reflection principle (Wikipedia "Radical probabilism," index, 2026-09-30).
- **Alternatives to single-number probability:**
  - **Dempster–Shafer theory** (Dempster 1967; Shafer, *A Mathematical Theory of Evidence*, 1976): belief functions returning **[belief, plausibility] intervals**, designed to separate *uncertainty from ignorance* — mass can sit on "don't know" (Θ) instead of being forced onto specific hypotheses; Dempster's rule combines independent evidence. It generalizes probability: tighten the disjunction axiom and you recover probability functions (SEP supplement, index, 2026-09-30).
  - **Imprecise probabilities** (Walley 1991): sets of distributions instead of one; **possibility theory** (Dubois & Prade).
- **LLM-era scoring:** verbalized confidence; calibration of neural networks (Guo et al. 2017 — modern nets are poorly calibrated; temperature scaling); uncertainty estimation for generated claims.

**How scores are revised over time as evidence accumulates.** Conjugate updating (beta-binomial: successes/failures shift the posterior mean and shrink variance); Kalman-style for continuous state. Sequential Bayesian updating is the natural "fluid certainty score" protocol: each observation is a message that sharpens the distribution. Jeffrey kinematics handles the realistic ledger case where the new "fact" itself arrives with less-than-certainty (a sensor reading, an LLM-extracted claim).

**Canonical references.**
1. de Finetti (1937); Savage, *The Foundations of Statistics* (**1954**) — subjective probability.
2. Jeffrey, *The Logic of Decision* (**1965**; 2nd ed. 1983) — probability kinematics / radical probabilism.
3. Dempster (1967); Shafer, *A Mathematical Theory of Evidence*, Princeton UP, **1976**.
4. Walley, *Statistical Reasoning with Imprecise Probabilities*, **1991**.
5. Bernardo & Smith; Gelman et al., *Bayesian Data Analysis* — practice (Gelman & Shalizi, "Philosophy and the practice of Bayesian statistics," arXiv:1006.3868, index, 2026-09-30).
6. Guo et al., "On Calibration of Modern Neural Networks," ICML **2017** — neural calibration.

**Practical notes / limitations.**
- **Need priors and likelihoods:** prior sensitivity; elicitation is hard; model misspecification produces *confidently wrong* posteriors.
- Dempster's rule gives counterintuitive results under high conflict (Yager's conflict-to-Θ rule and others proposed; human subjects behave between the two — Golden 1993/4, per Cambridge JDM article, index, 2026-09-30); mass functions blow up exponentially (2ⁿ values for n alternatives — exceeds working memory fast, same source).
- Bayesian convergence assumes the true hypothesis is in the support and evidence is genuinely informative; adversarial or misspecified likelihoods break it.
- LLM verbalized confidences are poorly calibrated out of the box; calibration must be measured on a frozen eval set and re-measured as distributions shift (mrsameerkhan production-RAG-ops doc, index, 2026-09-30).

## 8. LLM Context and Memory Management ("Context Cleanup")

**Core mechanism — four lines of attack.**

1. **Memory hierarchies (MemGPT/Letta).** Packer et al., "MemGPT: Towards LLMs as Operating Systems" (arXiv:2310.08560, **2023**, UC Berkeley): treat the context window like RAM and external stores like disk. Three tiers — **Core memory** (always in context: persona, key facts; editable by the agent), **Recall memory** (recent conversation, searchable), **Archival memory** (external DB, retrieved on demand). The agent manages its own memory via function calls; a **memory-pressure interrupt** forces summarization/eviction when the window fills. **Letta** is the productionized, open, self-hostable successor. Motivation: bigger windows are quadratically expensive *and* models ignore the middle of long contexts ("lost in the middle"), so allocation beats capacity (atharvax16 MemGPT study notes; haozhe-xing agent-learning chapter, index, 2026-09-30).
2. **Summarization / distillation.** Rolling compaction at token thresholds; hierarchical summarization of older turns (e.g., MCOS-style: core ~600–2000 tokens pinned, recall compacted at 8K, archival top-K(5) per turn) (morainet/mcos memory doc, index, 2026-09-30).
3. **Consolidation & forgetting (offline beats write-time).**
   - **Generative Agents** (Park et al., UIST **2023**): **memory stream** = timestamped append-only log of observations; retrieval scored by **recency** (exponential decay) + **importance** (LLM-rated 1–10 at creation) + **relevance** (embedding cosine); **reflection** triggered when summed importance of recent events exceeds a threshold (150): the agent poses salient questions, answers them from retrieved memories, stores insights *with pointers to the evidence* — a **reflection tree** (leaves = observations, internal nodes = inferences). Ablations: removing reflection degraded believability (edmund-harness memory-architecture research note; cerebro agent-memory-architectures note, index, 2026-09-30).
   - **Letta sleep-time compute:** dual-agent design — the primary agent *cannot* edit core memory; an offline **sleep-time agent** rewrites shared blocks (`rethink_memory`). Explicit motivation: MemGPT-style incremental self-editing "became messy and disorganized over time." Pareto improvement in quality at lower interaction-time latency/cost (same note, index, 2026-09-30).
   - **MemoryBank:** Ebbinghaus forgetting-curve decay + access reinforcement (frequently retrieved memories strengthen — retrieval-practice effect) (haozhe-xing chapter, index, 2026-09-30).
   - CoALA (Sumers et al. 2024): cognitive-science taxonomy — working, episodic, semantic, procedural memory; most frameworks implement only working + one external store (cerebro note, index, 2026-09-30).
   - Reflexion (Shinn et al., NeurIPS 2023): verbal self-reflection on failures in an episodic buffer — storing the *reflection* beats storing the failure.
4. **RAG source-document invalidation (the stale-index problem).** A vector DB is frozen in time; stale chunks ground confident wrong answers indistinguishable from hallucination. Production strategies (dev.to RAG-freshness guide; rag-interview-system stale-index doc; systology retrieval principles, index, 2026-09-30):
   - **Change detection by content hash:** re-crawl; re-chunk/re-embed only docs whose hash changed; stamp the rest as freshly verified — cost ∝ change, not corpus size.
   - **Deterministic chunk IDs** so re-indexing *replaces* rather than duplicates; garbage-collect chunks whose source disappeared (GC tied to document lifecycle — the "append-only index forever" anti-pattern).
   - **verified-at timestamps** on every chunk so retrieval/generation can filter or down-rank stale content; **TTL-based invalidation** (mark stale, re-embed on miss; background refresh sweep).
   - **Versioned indexes for embedder upgrades:** embeddings from different models live in different vector spaces (mixing = garbage similarity). Pattern: build v2 index in parallel → shadow traffic → A/B 10% → cutover → keep v1 for rollback → decommission in 2–4 weeks; tag vectors with `embedder_version` (mrsameerkhan production-RAG-ops doc, index, 2026-09-30).
   - **Cache invalidation:** versioned cache keys (`v{cache_version}` bumped on any doc change) + explicit delete-on-change + TTL safety net; fail-open on cache outage (harshith-star rag-document-intelligence-platform, index, 2026-09-30).
   - **Monitoring:** recall@5 on a frozen labeled eval set (alert on >5% weekly drop); top-1 similarity distribution drift; document coverage (never-retrieved docs are stale/irrelevant).
5. **Parametric knowledge editing** (for completeness): ROME (Meng et al. 2022 — causal tracing, rank-one MLP updates), MEMIT (2023 — batched multi-layer edits, thousands of facts), MEND. Suffers off-target effects and catastrophic forgetting in continual settings — not the SOTA for keeping *working context* accurate ("Memory in the Age of AI Agents," arXiv:2512.13564, index, 2026-09-30).

**Closest existing system to the ledger's goal:** **Zep/Graphiti** — bitemporal knowledge graphs for agents: every edge carries **event time** (when true in the world) + **ingestion time** (when observed), enabling non-lossy retroactive correction and fact invalidation/supersession, with hybrid semantic+BM25+graph retrieval at P95 ≈ 300ms and no LLM calls at retrieval (agentx memory-recall research note, index, 2026-09-30). This is topics 1 + 8 fused.

**State of the art (2026) for keeping working context accurate:** retrieval-side freshness (hash-based change detection, versioned indexes, verified-at metadata) is the production-grade answer for RAG; for agent memory, hierarchical paging (Letta) + **offline consolidation** (sleep-time compute / reflect stages — e.g., Hindsight's 91.4% LongMemEval attributed largely to its offline reflect stage: dedup, contradiction reconciliation, entity-profile construction) beats write-time extraction (edmund-harness note, index, 2026-09-30). Frontier gap: **no production system runs a formal classical TMS at LLM-KG scale**; engineered detect-then-resolve pipelines (CRDL) and dual-memory routing (WISE) substitute for dependency-directed justification tracking (davidamitchell 2026 survey, index, 2026-09-30).

**Practical notes / limitations.**
- Lost-in-the-middle: long contexts degrade; summarization loses detail and can introduce drift/hallucination.
- Self-edited memory becomes messy/disorganized over time (motivated Letta's sleep-time compute).
- Embedder upgrades force full re-indexing; mixing versions silently breaks retrieval.
- Staleness monitoring (drift metrics, frozen eval sets) is immature in most deployments.
- Frontier LLMs measurably violate AGM rationality postulates under iterated belief revision — the reasoner itself is the weak link in any justification-tracking scheme (davidamitchell survey, index, 2026-09-30).

---

## Could Not Verify

- **"Trigger problem" as a named formalism:** the mission's phrase did not resolve to a single named theory in the literature I could verify. I reconstructed the answer from adjacent formalisms (DBSP deltas, provenance semirings, self-maintainability, Bazel early cutoff, ASC 350 triggering events). If the requesting agent had a specific "trigger problem" source in mind (e.g., in active-database rule triggering — Widom/Minker lineage), that would need a follow-up search.
- **Quantitative scaling numbers for ATMS/JTMS** beyond the exponential worst-case characterization: the UBC complexity paper establishes the blowup qualitatively; I did not find verified benchmark numbers and did not want to invent them.
- **Letta sleep-time compute** details are from a 2026 research note citing Letta's blog/paper; I did not verify against Letta's primary docs.
- All findings are `index`-level (search-result page text), not `verified live` in an interactive browser. Canonical paper facts (authors/venues/years) are corroborated across multiple independent sources each.

## Sources

Per-topic note files in `notes/` (each: URL, read date 2026-09-30, `index` flag, key facts):
- `notes/topic-01-bitemporal.md`
- `notes/topic-02-belief-revision.md`
- `notes/topic-03-tms.md`
- `notes/topic-04-event-sourcing.md`
- `notes/topic-05-incremental.md`
- `notes/topic-06-trigger-problem.md`
- `notes/topic-07-epistemic-scoring.md`
- `notes/topic-08-llm-memory.md`

Key URLs (verbatim, as returned by search):
- https://github.com/adrianco/the-goodies/blob/HEAD/docs/adr/ADR-014-temporal-prior-art-and-platform.md
- https://github.com/bmf-san/bmf-tech/blob/HEAD/content/en/posts/nontemporarl-unitemporal-bitemporal-design.md
- https://github.com/ekgardt/llm-wiki/blob/HEAD/docs/research/2026-08-28-bitemporal-claims.md
- https://huber.artsci.utoronto.ca/wp-content/uploads/2013/07/Belief-Revision-I-The-AGM-Theory.pdf
- https://github.com/xyzzylabs/dent8/blob/HEAD/docs/belief-revision.md
- https://www.cs.ubc.ca/sites/default/files/tr/1988/TR-88-11.pdf
- https://www.qrg.northwestern.edu/papers/Files/QRG_Dist_Files/QRG_1988/Forbus_1988_Focusing_the_ATMS.pdf
- https://cdn.aaai.org/AAAI/1986/AAAI86-151.pdf
- https://github.com/microsoftdocs/architecture-center/blob/HEAD/docs/patterns/event-sourcing.md
- https://github.com/robsonkades/agent-skills/blob/HEAD/skills/event-sourcing/SKILL.md
- https://www.researchgate.net/publication/359647360_DBSP_Automatic_Incremental_View_Maintenance_for_Rich_Query_Languages
- https://github.com/ampersandtarski/ampersand/blob/HEAD/memorybank/incremental-evaluation/ecosystem-and-video.md
- https://www.cs.cmu.edu/~rwh/students/acar.pdf
- https://github.com/parnmanas/ai-workflow-board/blob/HEAD/docs/ontology-graph/research-incremental.md
- https://dev.to/jakeherringbone/bazel-what-you-give-what-you-get-5a91
- https://www.valuationresearch.com/insights/triggering-event-impairment-testing/
- https://en.wikipedia.org/wiki/Radical_probabilism
- https://plato.stanford.edu/archIves/win2023/entries/logic-inductive/sup-uncertain-inf.html
- https://arxiv.org/pdf/1006.3868
- https://github.com/atharvax16/til/blob/HEAD/papers/LLVM/MemGPT/memgpt-study-notes.md
- https://github.com/deibler/edmund-harness/blob/HEAD/docs/research/memory-architecture-2026-07-28.md
- https://github.com/qr-madness/agentx/blob/HEAD/todo/research/2026-07-memory-recall-research.md
- https://dev.to/promptcloud_services/scraping-for-rag-keeping-your-retrieval-index-fresh-and-why-staleness-hallucinates-3km8
- https://github.com/mrsameerkhan/sameerkhan/blob/HEAD/10.mlops/13_production_rag_ops.md
- https://github.com/davidamitchell/research/blob/HEAD/progress/2026-07-20-autonomous-knowledge-curation-truth-maintenance.md
