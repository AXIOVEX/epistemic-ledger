# The Living Epistemic Ledger — Framing Paper

**Status:** research framing, first issued 2026-09-30. The design it framed has since been built — see the status addenda at the end of this paper (prototype v0.11.1). The framing sections that follow are the surveyed ground on which the design was built; their wording was lightly revised in a plain-language pass on 2026-10-12 (language only, all figures unchanged), and nothing in them was decided architecture when they were written.

## 1. The problem

Databases are deeply flawed: there is no built-in way to keep challenging the data, to know how true any of it is, or to update it as the evidence comes in. A record is written, and from then on it sits — unexamined, unversioned in meaning, silently going stale while decisions compound on top of it.

The same flaw appears in evaluation. Score a conclusion once, call it final, and you have frozen a judgment made with yesterday's evidence. When new facts arrive, nothing forces a revisit — and nothing records that the old judgment was ever superseded.

## 2. The proposal

A living epistemic ledger with four properties:

1. **Append-only records.** Conclusions are never mutated or deleted. A correction is a new record that supersedes the old one; the full history of what was believed, and when it was believed, remains queryable.
2. **Fluid certainty scores.** Every conclusion carries a score that moves as evidence accumulates — the probability you end with today is the one you start from tomorrow — replacing one-time yes/no verdicts.
3. **Dependency-tracked revisits.** Each conclusion records *why* it is held. A new fact propagates along the dependency graph; exactly the conclusions it touches — plus their dependents — are re-evaluated.
4. **A trigger discipline.** Not every new fact warrants a revisit. The system needs a principled, layered answer to *when* recomputation is required.

In one sentence: a living epistemic scoring system where every conclusion lives in an append-only database with a fluid certainty score, and new facts automatically trigger re-evaluation of the conclusions — and their dependents — that they affect, instead of any judgment ever being final.

## 3. Research foundations

Eight threads were surveyed (2026-09-30; raw notes with provenance in `docs/research/`). Each is summarized as mechanism, canonical references, and limitations relevant to the ledger.

### 3.1 Bitemporal data modeling

**Mechanism.** Every fact carries two independent intervals: *valid time* (when it held in the world) and *transaction time* (when the system learned it). Retroactive correction = close the old record's transaction-time interval, insert a new row with past valid time and current transaction time. Nothing is ever mutated; a query scoped to an earlier transaction time still returns the pre-correction answer.

**Canonical.** Snodgrass & Ahn, "A Taxonomy of Time in Databases," SIGMOD 1985; Jensen et al., "The Consensus Glossary of Temporal Database Concepts," LNCS 1399; Allen, "Maintaining Knowledge about Temporal Intervals," CACM 1983; SQL:2011 application-time / system-time tables. Production: XTDB, Datomic.

**Limitations.** Two-axis querying is harder to index and reason about; full bitemporality only pays off where the past can actually be corrected ("bitemporal-lite" — valid-time state plus transaction-time audit — is a defensible compromise).

### 3.2 Belief revision (AGM)

**Mechanism.** Three operations on a belief set K: *expansion* (add), *contraction* (remove), *revision* (add while restoring consistency). The Levi identity reduces revision to contraction-by-the-negation followed by expansion. *Epistemic entrenchment* orders beliefs so that on conflict, the least-entrenched give way — the principled "what to give up" rule.

**Canonical.** Alchourrón, Gärdenfors & Makinson, JSL 1985; Gärdenfors, *Knowledge in Flux*, MIT Press 1988; Katsuno & Mendelzon 1991; Hansson, *A Textbook of Belief Dynamics* 1999 (belief *bases* — the implementable variant, where the disputed Recovery postulate fails).

**Limitations.** Logical omniscience (no real agent is deductively closed); the theory is episodic, with no deliberation between alternatives; repairing an inconsistent ontology (the system's web of categories and relations) is NP-hard or worse, meaning no efficient general procedure exists; LLMs show systematic belief-revision failures (Belief-R benchmark: models "incapable of revising their prior beliefs," arXiv:2406.19764) and coherence-norm violations (arXiv:2406.03442) — no located study tests the AGM postulates directly, so the weaker, sourced claim is used.

### 3.3 Truth maintenance (JTMS / ATMS)

**Mechanism.** Nodes are beliefs carrying *justifications* — the antecedents (and absences) they rest on. Doyle's JTMS (1979) maintains one consistent context with IN/OUT labels and dependency-directed backtracking: a contradiction traces the justification graph to the culprit assumptions and retracts exactly those. De Kleer's ATMS (1986) maintains many contexts at once via minimal assumption-set labels plus a database of "nogoods" — combinations of assumptions already known to contradict each other; derivations are never retracted, only contexts selected.

**Canonical.** Doyle 1979; de Kleer 1986; de Kleer & Williams, AAAI 1986; de Kleer, "Focusing the ATMS," 1988; Forbus & de Kleer, *Building Problem Solvers*, MIT Press 1993.

**Limitations.** ATMS label sets can grow exponentially in the number of assumptions (the parity problem); no production system runs a classical TMS at LLM–knowledge-graph scale — engineered detect-then-resolve pipelines substitute. The durable pattern for the ledger: track *why* each belief is held; propagate retraction through the support relation; retain a claim while one complete justification survives.

### 3.4 Event sourcing

**Mechanism.** Every state change is an immutable event in an append-only log; current state is derived by replay. Corrections are *compensating events* — the reversal itself becomes part of the auditable record. Controlled, audited stream rewrites are the rare exception, never the norm.

**Canonical.** Greg Young; Fowler, "Event Sourcing," 2005; Microsoft Azure Architecture Center, "Event Sourcing pattern."

**Limitations.** Unbounded stream growth (snapshots, stream closure); schema evolution (old events must stay interpretable); projections are eventually consistent; immutability trades against redaction/privacy.

### 3.5 Incremental recomputation

**Mechanism.** Record fine-grained dependencies; on input change, push deltas forward along the dependency graph, recompute only affected nodes, and halt when outputs stabilize (*early cutoff*). The formal peak is DBSP (Budiu, Chajed, McSherry, Ryzhyk & Tannen, VLDB 2023). In plain terms, it turns any streaming query into an incremental one — differentiate the inputs, apply the query's change rules, integrate the result back (written SΔ = D ∘ S ∘ I) — where every row carries an integer weight (+1 for an insertion, −1 for a retraction), so additions and removals run through the same machinery; the weighted rows are called Z-sets. Provenance semirings (Green et al., PODS 2007) give the algebraic "why does this output depend on that input."

**Canonical.** Gupta, Mumick & Subrahmanian, SIGMOD 1993 (counting algorithm, DRed); Gupta & Mumick survey 1995; Koch et al., DBToaster, VLDB J. 2014; McSherry et al., "Differential Dataflow," CIDR 2013; Acar, "Self-Adjusting Computation," CMU PhD 2005; Bazel's content-addressed action cache with early cutoff.

**Limitations.** Retained state is the cost center; higher-order IVM can demand O(N²) auxiliary space; non-invertible aggregates (MIN/MAX) need auxiliary structures on retraction; getting delta rules wrong yields *silent* divergence — precision is a correctness requirement.

### 3.6 Change-impact analysis — the trigger problem

**Mechanism.** Three layers, coarsest to most precise: (1) *dirty-flagging* — mark changed inputs, recompute everything downstream (sound, over-invalidates); (2) *precise invalidation* — recompute only when an input's *value* actually changed (Bazel early cutoff; salsa/rustc verifying traces); (3) *materiality thresholds* — even a real change may not warrant action (sensitivity analysis; domain rules like ASC 350's triggering-event test at >50% impairment probability; thresholds tuned empirically, e.g. 8–15 flagged items per review cycle). Formally, "this fact does not affect that conclusion" is exactly the case where DBSP's change calculation (its delta) comes out empty — Δ = ∅, nothing downstream moves. Provenance annotations give the formal "why."

**Limitations.** No single formalism covers the judgmental side — materiality stays domain-specific and needs re-tuning as scale changes. Precise invalidation demands exact dependency information and deterministic recomputation.

### 3.7 Non-binary epistemic scoring

**Mechanism.** Start from credences — stated degrees of belief — treated as probabilities, and update them in Bayesian fashion as evidence arrives in sequence: the probability you end with today is the one you start from tomorrow. *Jeffrey conditionalization* (also called probability kinematics) handles the realistic case where the new "fact" itself arrives with less-than-certainty: rather than accepting it outright, you shift your probabilities by the amount the evidence supports. Dempster–Shafer belief/plausibility intervals represent ignorance explicitly (mass can sit on "don't know"); imprecise probabilities use sets of distributions.

**Canonical.** de Finetti 1937; Savage 1954; Jeffrey, *The Logic of Decision* 1965; Dempster 1967; Shafer 1976; Walley 1991; Guo et al., "On Calibration of Modern Neural Networks," ICML 2017.

**Limitations.** Priors and likelihoods must be elicited; misspecification produces confidently-wrong posteriors; Dempster's rule misbehaves under high conflict, and its mass functions (the weights it assigns to sets of possibilities) grow exponentially in number; LLM verbalized confidences are poorly calibrated out of the box.

### 3.8 LLM memory and context cleanup

**Mechanism.** Four lines of attack: (1) *memory hierarchies* — MemGPT/Letta treat context as RAM with core/recall/archival tiers and memory-pressure interrupts; (2) *summarization/distillation* — rolling compaction; (3) *offline consolidation beats write-time extraction* — Letta's sleep-time compute rewrites memory blocks offline because, with incremental memory formation, memories "may become messy and disorganized" over time (Letta's words); Generative Agents' reflection trees trigger on accumulated importance; (4) *RAG freshness* — content-hash change detection, deterministic chunk IDs with garbage collection, verified-at timestamps, TTL invalidation, versioned indexes for embedder upgrades, drift monitoring on frozen eval sets.

**Closest existing systems to the ledger:** Zep/Graphiti bitemporal knowledge graphs — every edge carries event time plus ingestion time, enabling non-lossy retroactive correction and fact invalidation/supersession. Several 2026 systems sit as close on other axes: TOKI, a bitemporal system for resolving contradictions in agent memory whose audit rows preserve the losing fact; SodaMem, a temporal graph memory whose facts carry provenance spans and supersedes/contradicts edges; Engram, a bi-temporal memory engine that resolves contradictions by invalidation, never deletion, so every fact keeps provenance and a supersession chain; and MemTX, a transactional belief-commit protocol whose records declare their parents, so retracting a belief triggers repair of the records derived from it. None of these carries a certainty score that is revised as evidence accumulates — TOKI and MemTX stamp a confidence value at write time (TOKI uses it to pick conflict winners; MemTX to pass an admission threshold), but the value does not move with the evidence — and none has the ledger's layered rule for when a change warrants revisiting the conclusions that depend on it. The combination in §2 is, as far as we have found, still the ledger's own.

**Limitations.** Summarization loses detail and can drift; self-edited memory degrades without offline consolidation; no formal TMS runs at LLM scale; LLMs fail belief-revision benchmarks and coherence norms (arXiv:2406.19764, arXiv:2406.03442) — the reasoner is the weak link in any justification-tracking scheme.

## 4. Convergences

- **Append-only correction appears three ways** — bitemporal supersede rows, compensating events, TMS justifications — one pattern in three clothes. The ledger should pick one discipline and hold it everywhere.
- **"Which conclusions must be revisited" has two formal answers** — ATMS environments/nogoods (symbolic) and DBSP delta propagation (dataflow) — both with exponential/state blowup failure modes. The ledger needs the dependency discipline of the former with the value-based cutoff of the latter, and must budget for the blowup from day one.
- **Fluid certainty = sequential Bayes with Jeffrey kinematics** — probabilities updated step by step as evidence arrives, softening the update when the new evidence is itself uncertain — with Dempster–Shafer available where ignorance must be represented explicitly rather than spread across hypotheses.
- **The trigger problem is the least-formalized part** and therefore the ledger's main design risk: dirty-flagging, precise invalidation, and materiality thresholds are a ladder, not a solution, and the top rung is always domain judgment.

## 5. Open questions

1. What is the ledger's native record schema — bitemporal tuples, events, or both?
2. What scoring calculus: single credences, intervals, or sets of distributions?
3. Where does the materiality threshold live, and who tunes it?
4. How are justifications captured for conclusions produced by LLMs, which fail belief-revision benchmarks under iteration?
5. What is the query language — "what did we believe at time T," "what changed between T1 and T2," "what depends on fact F"?
6. What are the ledger's own kill criteria — how would we know the design is failing?

## 6. Roadmap

1. **Framing** (this paper) — done.
2. **Record schema + scoring calculus** — decide §5.1–5.2 on paper first.
3. **Minimal prototype** — append-only store, bitemporal queries, one dependency-propagated revisit loop, one materiality rule.
4. **Trigger discipline** — implement the three-layer ladder; measure over/under-invalidation.
5. **LLM context application** — apply the ledger as a context-cleanup substrate and measure staleness reduction.

## Status addendum — 2026-10-02

The roadmap above has been executed. Phase 2 was decided as *both*: immutable events as the write model, and bitemporal claim tuples as the read projection (each claim stamped with both its valid time and its transaction time); single credences natively, Dempster-Shafer intervals as an option (Design Memos 01-04). Phase 3 shipped as a working prototype (v0.10), with governance the original roadmap did not foresee: writer tiers, signed verdicts, escalation, named-graph authority ceilings (limits on what any one named partition of the graph may assert), and post-state predicate policies (rules checked against the state after each write) (Memos 06, 10, 11). Phase 4 measured the trigger ladder (TRIGGER-STRESS-01) against an exact, non-incremental reference computation (the oracle): at epsilon 0.005 the ladder reached recall 0.960 and precision 0.715 — it caught 96.0% of the conclusions that truly needed revisiting, and 71.5% of the revisits it triggered were warranted. Phase 5 measured how much staleness the ledger removes in an adversarial newsroom (a test workload of deliberately hostile news copy): 20.8-22.2% of baseline errors eliminated overall, and 51-61% on derived claims. Real LLM extraction and consolidation were validated first on hosted models and then ported to a free local model at equal quality (LOCAL-EXTRACTION-01, LOCAL-CONSOLIDATION-01), and stress-tested on non-template prose (FREETEXT-01) and on prose written by a different model family (INDIE-CORPUS-01: 21.1% overall / 49.7% derived, seed record 4/5 — the earlier authorship caveat is retired). The kill bars — the pre-set failure thresholds that would end the design — have since been re-measured across every workload family (KILL-BARS-01: two flag bars were adjusted under a rule stated in advance; the Brier bar, the accuracy threshold for probability forecasts, held at its definitional chance value). The store was then hardened without semantic change (v0.11, Design Memo 12: single-writer lock, an fsync'd event log — every event forced to disk before the write counts as done — and replay verification). Two of section 5's questions remain genuinely open: the override-rate bar (the pre-set limit on how often a human reviewer may override a score) has no human-in-the-loop workload to calibrate it against, and no deployment beyond the prototype exists yet. Per-report agent tempering, the one tuning fix proposed along the way, was tested and refuted (CALIBRATION-01).

## Status addendum — 2026-10-09

Three developments since the addendum above. First, the override loop is closed mechanically and measured: v0.11.1 propagates manual scores through the revisit loop (previously they updated a single claim), and OVERRIDE-CAL-01 calibrated the override-rate bar against scripted reviewer personas (observed 0.020-0.035 against the 0.20 bar). The human-in-the-loop calibration named above remains genuinely open — personas are simulations, and the record says so.

Second, the extraction boundary — how faithfully the system can pull claims out of real text — was measured on real published copy and became the program's center of gravity. REALWIRE-01 showed that verbatim published sentences collapse local extraction to 0.481: the model fact-checks the sentence instead of reporting the stance it expresses, while the ledger's bookkeeping advantage survives in compressed form. STANCE-01 and STANCE-02, run as frozen diagnostic studies, isolated the mechanism as proposition-prior interference — the model's own prior belief about a claim interferes with reading the stance the text takes toward it, and the interference grows with familiarity (a dose-response pattern). They also mapped three distinct coverage sinks in structured protocols (three separate places where claims were being lost), and established that a hosted frontier model performs the task at ceiling (0.977) — the failure is the local model's fidelity, not the definition of the task. A post-freeze proof package then re-measured the remedies downstream: a base-model upgrade alone (Qwen3.5-9B, identical prompts) reduces downstream ledger error from 0.4637 to 0.3194, structured variants do not separate from it outside seed noise (the random variation between runs), and the frontier arm (0.1802) remains the only strong-band configuration. The production recommendation is recorded in the STANCE-02 report.

Third, the measured defaults have been ported out of the prototype into the deterministic Applied Epistemic Engineering engine (aee, now at version 1.5.3) and its Spec Kit extension (now at version 1.5.2) — policy gates with forced abstention (the system must decline to score when its gates are not met), per-source measured reliability, materiality review queues — each default citing the measurement it came from. Two successor studies then tested whether a small trained adapter could close the local model's stance gap directly, each run under frozen held-out discipline with its test data sealed before training. LORA-01 improved held-out assertion accuracy (0.903 to 0.972) but missed the improvement bar set for it in advance and learned to abstain on real published copy. LORA-02, redesigned around that failure, fixed every held-out assertion error yet abstained on 30 percent of the real corpus and damaged deny accuracy there. Both were killed under the criteria frozen before they ran: stance training on authored sentences does not transfer to real published copy, and the production default remains the unadapted Qwen3.5-9B. The ledger itself remains single-writer and undeployed beyond the prototype, deliberately.

---

*Research conducted 2026-09-30 (index-level: web search page text, cross-checked across 2+ independent sources per topic). Primary-source verification pass 2026-10-01 via arXiv/OpenAlex APIs: see `docs/research/BIBLIOGRAPHY.md` for the annotated bibliography, verification statuses, and one correction applied (LLM/AGM claim softened to the sourced weaker claim). Raw notes with provenance: `docs/research/`.*
