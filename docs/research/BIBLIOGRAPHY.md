# Annotated Bibliography — primary-source verification

**Date:** 2026-10-01. **Method:** arXiv API + OpenAlex API + targeted web verification.
Each entry carries a verification status: **primary** (abstract/full text read),
**metadata** (existence + venue confirmed via OpenAlex), or **canonical**
(textbook-level work, corroborated across secondary sources, not re-verified here).

---

## 1. Bitemporal data modeling

- **Snodgrass & Ahn, "A Taxonomy of Time in Databases," SIGMOD 1985.** *canonical.* The valid-time / transaction-time distinction the ledger's schema rests on.
- **Jensen et al., "The Consensus Glossary of Temporal Database Concepts," LNCS 1399.** *canonical.* Shared vocabulary (bitemporal, etc.).
- **Allen, "Maintaining Knowledge about Temporal Intervals," CACM 1983.** *canonical.* Interval algebra.
- **Rasmussen, Paliychuk, Beauvais, Ryan & Chalef, "Zep: A Temporal Knowledge Graph Architecture for Agent Memory," arXiv:2501.13956 (Jan 2025).** *primary.* **Closest existing system to the ledger.** Every `EntityEdge` carries the bitemporal quartet — `valid_at`/`invalid_at` (event timeline T) and `created_at`/`expired_at` (transaction timeline T′) — formalized in §3 of the paper and confirmed against the source (`graphiti_core/edges.py`) by multiple independent code-level analyses. Contradictions are detected and resolved by *invalidation* (never deletion); notably, Graphiti persists **no explicit "contradicts" edge** — a design contrast with our explicit `contradiction` events. Reported 94.8% vs 93.4% (MemGPT) on DMR, up to ~18.5% gains on LongMemEval.
- **Brown, "Quipu: A Governed Bitemporal Knowledge Graph Store," arXiv:2608.16813 (Aug 2026).** *primary.* Published six weeks before this writing. Inverts four defaults of KG stores for agent workloads: gated writes, **everything bitemporal** (data, trust labels, verdicts, rules), named graphs as the unit of authority/trust, governance spec as facts in the store it governs. Deterministic evaluation (seeded "Census" lifecycle vs. planted ground truth). Directly relevant to the ledger's governance and audit story; read before designing ledger authorization.

## 2. Belief revision (AGM)

- **Alchourrón, Gärdenfors & Makinson, JSL 1985; Gärdenfors, *Knowledge in Flux*, MIT Press 1988.** *canonical.* Expansion/contraction/revision, epistemic entrenchment.
- **"AGM Belief Revision, Semantically," arXiv:2112.13557 (2021).** *metadata.* Active formal work continues.
- **"A modal logic translation of the AGM axioms for belief revision," arXiv:2502.14176 (2025).** *metadata.* AGM formalism still being extended this year.
- **"The logic of KM belief update is contained in the logic of AGM belief revision," arXiv:2602.23302 (2026).** *metadata.* Update-vs-revision relationship, live research.

## 3. Truth maintenance

- **Doyle, "A Truth Maintenance System," AI 1979.** *canonical.* JTMS: justifications, IN/OUT labels, dependency-directed backtracking.
- **de Kleer, "An Assumption-based Truth Maintenance System," AI 1986.** *canonical.* ATMS: assumption-set labels, nogoods, multi-context.
- **Forbus & de Kleer, *Building Problem Solvers*, MIT Press 1993.** *canonical.* The implementer's textbook.
- **"Possibilistic Assumption based Truth Maintenance System," arXiv:1303.5402 (2013).** *metadata.* ATMS variants still published; no production LLM-scale TMS found.

## 4. Event sourcing

- **Young (talks/essays); Fowler, "Event Sourcing," 2005.** *canonical.* Append-only log, replay, compensating events.

## 5. Incremental recomputation

- **Budiu, McSherry, Ryzhyk & Tannen, "DBSP: Automatic Incremental View Maintenance for Rich Query Languages," arXiv:2203.16684 (2022) / VLDB 2023.** *primary (OpenAlex metadata + abstract).* The formal peak: any streaming query's incremental version is SΔ = D ∘ S ∘ I; Z-sets unify inserts and retractions. (The 2024 OpenAlex hit is the SIGMOD Record retrospective by a subset of authors.)
- **"Incremental View Maintenance for Property Graph Queries," arXiv:1712.04108 (2017).** *metadata.* IVM on graph-structured queries — directly relevant if the ledger's support graph grows large.
- **"Recent Increments in Incremental View Maintenance," arXiv:2404.17679 (2024).** *metadata.* Recent survey; read before scaling the revisit loop.
- **McSherry et al., "Differential Dataflow," CIDR 2013; Gupta, Mumick & Subrahmanian, SIGMOD 1993 (DRed).** *canonical.* The lineage DBSP stands on.

## 6. The trigger problem

No single primary source found — consistent with the paper's claim that this is the least-formalized part. Ladder rungs are sourced separately: Bazel early cutoff (engineering), ASC 350 triggering-event test (accounting standard), salsa/rustc verified traces (engineering). **Gap acknowledged:** the judgmental/materiality rung has no formalism; it is domain practice.

## 7. Epistemic scoring

- **Jeffrey, *The Logic of Decision*, 1965.** *canonical.* Probability kinematics — the ledger's update rule for uncertain evidence.
- **Guo, Pleiss, Sun & Weinberger, "On Calibration of Modern Neural Networks," ICML 2017 (arXiv:1706.04599).** *metadata (OpenAlex exact match, 2,515 citations).* Poor out-of-the-box calibration — the reason scores are machine-maintained posteriors, never raw LLM vibes.
- **Shafer 1976; Dempster 1967.** *canonical.* Belief/plausibility intervals (opt-in in the ledger).
- **"Belief Revision: The Adaptability of Large Language Models Reasoning" (Belief-R benchmark), arXiv:2406.19764.** *primary (abstract).* Models "incapable of revising their prior beliefs"; update-vs-maintain tradeoff; prompting doesn't fix it. Direct support for treating LLM outputs as provisional evidence, never deductive justifications.
- **Hofweber, Hase, Stengel-Eskin & Bansal, "Are Language Models Rational? The Case of Coherence Norms and Belief Revision," arXiv:2406.03442 (2024).** *primary (abstract).* Coherence norms apply to some LMs but not others.
- **Betz & Richardson, "Probabilistic coherence, logical consistency, and Bayesian learning," PLOS ONE 2023.** *primary (abstract).* Pretrained rankers suffer global inconsistency; self-training can induce coherence — relevant to the learned-entrenchment story.
- **CORRECTION to PAPER.md:** the framing paper says "frontier LLMs measurably violate AGM postulates under iterated revision." The primary sources support *systematic belief-revision failures and coherence-norm violations*, but no located study tests the AGM postulates directly. Soften to the weaker, sourced claim.

## 8. LLM memory & context cleanup

- **Letta (ex-MemGPT) sleep-time compute (2025).** *primary (Letta blog + docs, corroborated by 4+ independent analyses; paper materials arXiv:2504.13171).* A **separate background agent** shares the primary agent's memory blocks and rewrites them asynchronously; the primary agent **cannot edit its own core memory**. Stated motivation, verbatim: "memories may become messy and disorganized" under incremental self-editing. Reported: Pareto improvement on math benchmarks, up to ~18% accuracy gains, ~2.5× cost-per-query reduction; heterogeneous models (fast/cheap live, strong/slow sleep). This upgrades the paper's claim from index-level to well-corroborated, and it validates the ledger's own offline `learn_entrenchment` pass as following the industry's direction.
- **Anthropic "Dreams" (managed agents, 2026).** *primary (secondary reporting of official docs).* Async pipeline: existing store + transcripts → NEW reorganized store; input never modified; reviewable, instructable. Non-destructive consolidation as the production design floor.
- **MemGPT (2023), Generative Agents reflection (2023), Mem0 decay (2026), Cognee pruning.** *canonical/secondary.* The memory-hierarchy and lifecycle lineage.
- **Zep/Graphiti (above).** The bitemporal agent-memory reference implementation.

---

## Verification summary

| paper claim | status after this dig |
|---|---|
| Graphiti/Zep is bitemporal (T and T′ per edge) | **confirmed primary** — paper §3 + code-level sources |
| Zep is the closest existing system | **confirmed** — no closer system found; Quipu (2026) is adjacent (governance, not memory) |
| Letta sleep-time: offline rewrite because self-editing gets messy | **confirmed primary** — Letta's own words |
| DBSP as the formal delta theory | **confirmed** — arXiv:2203.16684 / VLDB 2023 |
| LLM verbalized confidences poorly calibrated | **confirmed** — Guo et al. 2017, 2,515 citations |
| LLMs violate AGM postulates under iteration | **softened** — sources show belief-revision failures, not direct AGM-postulate tests |
| No production TMS at LLM scale | **holds** — no counterexample found; recent TMS work is possibilistic variants, not scale |
| Trigger problem has no single formalism | **holds** — no unifying source found |
