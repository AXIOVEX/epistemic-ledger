# Design Memo 02 — Entrenchment-based contradiction resolution

**Date:** 2026-10-01. **Status:** decided; implemented in `prototype/ledger.py` (v0.2).

Implements Design Memo 01 §3's deferred item: *"on conflict, epistemic entrenchment decides what gives way."*

## Decision

Contradictions enter **explicitly** — `declare_contradiction(a, b)` — not by automatic detection (deferred; detecting all contradictions is undecidable in general and a research project of its own). Resolution is entrenchment-ordered contraction:

1. Compare live entrenchments. **Tie → human.** Emit `contradiction_unresolved`; the item sits in the open-contradictions queue (counted in kill metrics). No silent coin-flips.
2. Otherwise the less-entrenched claim is the **loser** and is contracted against the winner via the ledger's existing Jeffrey machinery:
   - `new_L = jeffrey(score_L, p_loser_given_winner, score_L, score_W)`
   - `p_loser_given_winner` default **0.05**, elicited at declaration time.
   - `P(L|¬W) = score_L`: the winner's falsity tells us nothing new about the loser — the natural default, not a parameter.
3. The contraction is an ordinary `score_revision` (trigger = the contradiction event) plus a `contract` event naming loser/winner. Then the loser's **dependents are re-propagated** through `_revisit` — downstream beliefs weaken accordingly.
4. Events are immutable, so resolution is a separate `contradiction_resolved` event; open contradictions = declared minus resolved (event-sourced, no mutation).

Axiomatic-tier (1.0) claims need no special-casing: a 1.0 loser implies a 1.0 winner, which is a tie, which goes to a human.

## Entrenchment tiers (manual in v0.2; learned deferred to v0.3)

| tier | value | meaning |
|------|-------|---------|
| `axiomatic` | 1.0 | definitional; loses only to another 1.0 (→ human) |
| `measured` | 0.75 | directly observed / instrumented |
| `inferred` | 0.5 | default for derived conclusions |
| `provisional` | 0.25 | LLM-generated or single weak source |
| `deprecated` | 0.0 | superseded soon; loses every tie-break |

`apply_tier(claim_id, tier)` / `set_entrenchment(claim_id, value)` version the claim row bitemporally (same close+insert as score changes) and emit `entrenchment_set`. Facts from `ingest_evidence` keep entrenchment 1.0.

## Open (not decided here)

- Learned entrenchment (v0.3): derive from track record (Brier) rather than manual tiers.
- Automatic contradiction detection: probably via the LLM-consolidation pass, not the core loop.
- Whether contraction should also retract the loser's weakest support edge (dependency-directed backtracking) — currently score-only; the edge stays, so a later vindication can restore the score through the normal revisit loop.
