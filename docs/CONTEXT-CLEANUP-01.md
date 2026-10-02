# Context-Cleanup Experiment 01 — staleness reduction

**Date:** 2026-10-01. **Code:** `prototype/context/experiment.py` (seeded, 5 seeds).

## Question

Does the ledger, used as an agent's working memory, reduce staleness versus a frozen context?

## Method

Simulated world of 8 binary facts flipping at 5%/step. Derived conclusions form single-parent chains (F → D1 → D2; ground truth D1 = D2 = F). Two memories share identical semantics and the identical noisy observation stream (50% observation probability per fact per step, 90% correct, credence 0.8):

- **ledger-backed:** observations update fact claims; the revisit loop re-scores dependents automatically.
- **naive:** derived conclusions computed once from initial observations; never revised (the frozen-context baseline).

Both quizzed each step on all 16 derived conclusions vs. ground truth, 60 steps.

## Results

| seed | ledger err | naive err |
|------|-----------|-----------|
| 0 | 0.131 | 0.556 |
| 1 | 0.115 | 0.473 |
| 2 | 0.144 | 0.467 |
| 3 | 0.146 | 0.402 |
| 4 | 0.160 | 0.469 |
| **mean** | **0.139** | **0.473** |

**Staleness reduction: 0.334 — the ledger eliminates 70.6% of the frozen memory's errors**, consistent across all seeds. The residual ledger error (0.139) is observation noise (10% wrong observations) plus flip-then-not-yet-observed windows — irreducible without better sensing, not a ledger failure.

## Finding: the AND boundary (honest negative result)

An earlier version of this experiment used AND-structured derived beliefs (D true iff all supporters true). The ledger **lost** that version (0.403 vs 0.313). Root cause: per-edge independent Jeffrey does not compose into AND — each edge pulls toward the same posterior regardless of how many supporters hold. The naive baseline encoded the true AND directly, so the comparison measured model mismatch, not staleness.

This is a genuine expressiveness boundary of the v0.3 propagation model, not a bug: the ledger currently handles chains and single-parent dependencies exactly, but not joint/interacting evidence. Fixing it means joint likelihoods (noisy-AND/OR) on multi-parent nodes — recorded as future work, not patched mid-experiment.

## Addendum v0.4 — AND boundary closed (2026-10-01)

Re-ran the AND-structured variant with `noisy-and` combos on the derived nodes
(`python experiment.py and`):

| seed | ledger err | naive err |
|---:|---:|---:|
| 0 | 0.087 | 0.177 |
| 1 | 0.140 | 0.527 |
| 2 | 0.096 | 0.123 |
| 3 | 0.104 | 0.402 |
| 4 | 0.142 | 0.300 |
| **mean** | **0.114** | **0.306** |

**Staleness reduction: 0.192 — the ledger eliminates 62.8% of naive errors on
AND-structured beliefs.** Where v0.3 lost (0.403 vs 0.313), v0.4 wins. Joint
likelihoods (Design Memo 05) close the expressiveness boundary; per-edge
independent Jeffrey remains the default for single-parent chains.

## Limitations

- Toy world: binary facts, single-parent chains, thresholded answers.
- Both memories share the observation stream; real agents have retrieval failures too.
- The 70.6% figure is for this workload's flip/observation rates; it moves with them (slower flips → smaller gap; sparser observations → smaller gap).
- Real LLM context has retrieval, summarization, and attention dynamics this simulation doesn't model. This measures the *revision* half of context cleanup, not the full pipeline.
