# Topic 2 — Belief revision theory, AGM paradigm (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism
- Belief set K = a deductively closed set of sentences. Three change operations:
  - **Expansion** K+α = Cn(K ∪ {α}): add α, remove nothing.
  - **Contraction** K−α: remove α (unless tautology), add nothing.
  - **Revision** K∗α: add α while removing whatever is needed to restore consistency.
- **Levi identity** (Levi 1977): K∗α = (K−¬α)+α — revision reduces to contraction by the negation, then expansion. **Harper identity** (Harper 1976) gives the converse.
- **Minimal change / informational economy:** give up as little of K as possible. Formalized two ways:
  - *Partial-meet contraction:* intersect a selection of the maximal subsets of K that do not imply α.
  - *Epistemic entrenchment* (Gärdenfors–Makinson): a preference ordering over beliefs (transitivity, dominance, conjunctiveness, minimality, maximality) — on conflict, surrender the *least entrenched* belief that restores coherence. Core vs. peripheral beliefs.
- Postulates: contraction governed by Closure, Success, Inclusion, Vacuity, Extensionality, and the disputed **Recovery** (K ⊆ (K−p)+p); revision by 8 postulates (Closure, Success, Inclusion, Preservation, Consistency, Congruence, Conjunction 1 & 2). Katsuno & Mendelzon (1991) rephrased for finite bases (R1–R6) with a representation theorem via total pre-orders over worlds.
- **How a rational agent incorporates a contradicting new fact:** revision — accept the new sentence (Success), and retract the minimal, least-entrenched prior commitments needed for consistency. If the new fact is consistent with K, revision collapses to plain expansion (Vacuity/Preservation).
- **Belief base vs belief set** (Hansson): classical AGM works on closed sets and demands global consistency; belief-*base* revision works on finite, syntactic, non-closed sets; derived beliefs are recomputed, not stored; **Recovery fails** for bases. Hansson's **kernel contraction** is the base-level contraction operator.
- Iterated revision: the original postulates underdetermine sequences of revisions (Darwiche & Pearl and successors; "conditional preservation" principles).

## Canonical references
1. Alchourrón, Gärdenfors & Makinson, "On the Logic of Theory Change: Partial Meet Contraction and Revision," J. Symbolic Logic 50(2), 1985 — the AGM paper.
2. Gärdenfors, *Knowledge in Flux: Modeling the Dynamics of Epistemic States*, MIT Press, 1988 — book-length treatment incl. epistemic entrenchment.
3. Levi (1977) — Levi identity; Harper (1976) — Harper identity.
4. Katsuno & Mendelzon, "Propositional Knowledge Base Revision and Minimal Change," 1991 — finite/propositional reformulation + representation theorem.
5. Hansson, *A Textbook of Belief Dynamics* (1999) — belief-base revision, kernel contraction.
6. Huber, "Belief Revision I: The AGM Theory," Philosophy Compass 8/7 (2013) — clean postulate listing.

## Practical limitations
- **Logical omniscience:** belief sets are deductively closed — no real agent computes all consequences.
- Recovery postulate is famously disputed; fails for belief bases (the representation that matches implemented systems).
- AGM is **episodic**: "I had K; now I have K∗φ" — no notion of deliberating between alternatives or partial revision.
- Computational cost: repairing an inconsistent ontology is NP-hard or worse even in lightweight description logics; contraction uncomputable outside narrow logic classes.
- Gärdenfors' own triviality result: pairing revision with conditional reasoning collapses into inconsistency when both are made precise.
- Iterated belief revision is underdetermined by the core postulates; frontier LLMs measurably violate AGM rationality postulates under iterated revision (AGM-Bench / Belief-R, Wilie et al. 2024, per davidamitchell research note).

## Sources
- https://huber.artsci.utoronto.ca/wp-content/uploads/2013/07/Belief-Revision-I-The-AGM-Theory.pdf (full postulate listing for ∗1–∗8 and −1–−8, Levi/Harper identities, entrenchment)
- https://github.com/xyzzylabs/dent8/blob/HEAD/docs/belief-revision.md (Levi identity, six contraction postulates incl. Recovery dispute, belief-base vs belief-set, Hansson kernel contraction, epistemic entrenchment, JTMS/ATMS mapping)
- https://github.com/mijahauan/arisbe/blob/HEAD/docs/ALTERNATIVE_SET_INTELLECTUAL_HISTORY.md (entrenchment as core/peripheral; AGM's episodic limitation)
- https://github.com/nrdxp/predicate/blob/HEAD/docs/where-correction-ends.md (Gärdenfors triviality result; NP-hardness of ontology repair; Recovery/uncomputability)
