# Topic 3 — Truth maintenance systems (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism
- Nodes = beliefs; each node carries **justifications** (antecedent lists with IN/OUT conditions — a conclusion can depend on the *absence* of another belief, i.e., non-monotonic).
- **JTMS (Doyle 1979):** maintains **one** consistent context. Nodes labeled IN (believed) / OUT. When a premise changes or a contradiction is derived, the system re-propagates labels; **dependency-directed backtracking** traces the justification graph from the contradiction to find the culprit assumption(s) and retracts exactly those, rather than chronological backtracking. Retracting a premise automatically retracts everything that rested on it (unless an alternative justification survives).
- **ATMS (de Kleer 1986):** maintains **many** contexts at once. Every datum is labeled with the **minimal assumption-sets (environments)** under which it holds; **nogoods** record assumption-sets known to be inconsistent. The problem solver never retracts derivations — it just selects a consistent environment. Switching world-views is cheap (choose a different consistent environment); comparing alternatives is the ATMS's strength (e.g., VLSI design: CMOS vs gallium-arsenide elaborations explored in parallel).
- Retraction semantics: JTMS flips IN/OUT and re-propagates; ATMS interpretations are monotonic in the assumptions — adding a contradiction only adds nogoods, never deletes derived structure.
- Assumption-based dependency-directed backtracking (ADDB); "focusing" strategies (focus environments, implied-by consumers, contradiction consumers) keep the ATMS from exploring irrelevant contexts.

## Canonical references
1. Doyle, "A Truth Maintenance System," Artificial Intelligence 12(3), 1979 — JTMS.
2. de Kleer, "An Assumption-Based TMS," Artificial Intelligence 28(1), 1986 — ATMS.
3. de Kleer & Williams, "Back to Backtracking: Controlling the ATMS," AAAI 1986 — controlling search to one solution.
4. de Kleer, "Focusing the ATMS," 1988 — implied-by strategy for infinite domains.
5. Forbus & de Kleer, *Building Problem Solvers*, MIT Press, 1993 — textbook treatment.

## Practical limitations / scaling limits
- **ATMS label blowup:** label sets can grow **exponentially in the number of assumptions/database literals** (the "parity problem"; UBC TR-88-11, "The Computational Complexity of Assumption-Based Truth Maintenance Systems"). De Kleer's incremental-generation fix stops generating all solutions at once but "there is no way to stop the generation of the full (exponential) label set." The *problem of encoding*: efficiency depends entirely on how the problem solver encodes assumptions/clauses/consumers — "most ATMS users have to face this problem."
- **JTMS:** non-monotonic justification cycles can cause thrashing/relabeling loops; maintaining one consistent context means a wrong early choice forces expensive backtracking; both systems assume hand-encoded propositional justifications.
- Naive dependency-tracking schemes that stay complete are exponential in the number of retractions absorbed (justification structure grows with history; every retraction walks it).
- **No production system runs a formal classical TMS at LLM–knowledge-graph scale** (2026 research survey by davidamitchell): engineered substitutes instead — detect-then-resolve pipelines (CRDL), dual-memory routing (WISE). Frontier LLMs measurably violate AGM rationality postulates under iterated belief revision.
- Practical relevance today: nogood databases, conflict-driven clause learning (CDCL SAT solvers are the industrial heir), and the general pattern "track why each belief is held; propagate retraction through the support relation; retain a claim while one complete justification set survives."

## Sources
- https://www.cs.ubc.ca/sites/default/files/tr/1988/TR-88-11.pdf (UBC TR-88-11: ATMS computational complexity, parity problem, exponential label sets, problem of encoding)
- https://www.qrg.northwestern.edu/papers/Files/QRG_Dist_Files/QRG_1988/Forbus_1988_Focusing_the_ATMS.pdf (de Kleer, "Focusing the ATMS" 1988: implied-by strategy, focus environments)
- https://cdn.aaai.org/AAAI/1986/AAAI86-151.pdf (de Kleer & Williams, "Back to Backtracking: Controlling the ATMS," AAAI 1986)
- https://github.com/davidamitchell/research/blob/HEAD/progress/2026-07-20-autonomous-knowledge-curation-truth-maintenance.md (survey: no production classical TMS at LLM-KG scale; CRDL/WISE substitutes; AGM-Bench/Belief-R violations)
- https://github.com/nrdxp/predicate/blob/HEAD/docs/where-correction-ends.md (exponential-in-retractions cost of complete dependency tracking)
