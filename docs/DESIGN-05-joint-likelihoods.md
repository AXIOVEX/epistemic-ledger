# Design Memo 05 — Joint likelihoods (noisy-AND / noisy-OR)

**Date:** 2026-10-01. **Status:** decided; implemented in `prototype/ledger.py` (v0.4).

Closes the expressiveness boundary measured in CONTEXT-CLEANUP-01: per-edge independent Jeffrey does not compose into AND — each edge pulled toward the same posterior regardless of how many supporters held.

## Decision

Claims may carry a **combination function** over their parents' scores, replacing sequential Jeffrey for that node:

- **noisy-and:** `score = leak + (1−leak) · Πᵢ (sᵢ·pᵢ + (1−sᵢ))`
  All parents true (s=1) → 1; any parent false → leak. The AND the context experiment needed.
- **noisy-or:** `score = 1 − (1−leak) · Πᵢ (1 − sᵢ·pᵢ)`
  Any parent true → 1; all false → leak.

`sᵢ` = per-parent strength (default 1.0, stored on the support edge); `leak` = base rate independent of parents (default 0.0). Products commute, so combination is **order-independent** — unlike sequential Jeffrey, no application-order hazard.

## Integration with the revisit loop

In `_revisit`, a combo node recomputes from *all* parents' current scores (updated value if the parent changed this pass, else live) whenever **any** parent changed; otherwise it is skipped. Delta vs. epsilon applies as usual. Combo and per-edge Jeffrey coexist: a node uses one or the other.

## What this does not do

- No **leak learning** yet — leak is set at `set_combo` time.
- No joint *elicitation* UI; strengths come from `add_support(..., strength=)` or `set_combo`'s strengths map.
- Nodes with 0 live parents and a combo keep their score (no information to combine).

## Validation

The AND-structured context experiment is re-run with noisy-and on the derived nodes (`prototype/context/experiment_and.py`): the boundary is closed — ledger matches the AND ground truth where v0.3 lost.
