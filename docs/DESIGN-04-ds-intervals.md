# Design Memo 04 — Dempster–Shafer intervals: keep-or-cut

**Date:** 2026-10-01. **Status:** decided KEEP (opt-in); implemented in `prototype/ledger.py` (v0.3).

Answers Design Memo 01 §9's open question: *"whether D–S intervals earn their keep or get cut."*

## The experiment

Two cases, same point credence (0.5), different intervals:

| case | evidence | interval | ignorance |
|------|----------|----------|-----------|
| A: no evidence | none | [0.000, 1.000] | 1.000 |
| B: conflicting strong evidence | pass @0.8 vs fail @0.8 (K=0.64) | [0.444, 0.556] | 0.111 |

A point-credence policy decides both by coin flip — it cannot distinguish "no idea" from "confident it's close." An ignorance-gated policy (abstain iff ignorance > 0.5, else decide by Bel > 0.5) **abstains on A and decides on B**. The interval changes the decision; the point credence cannot.

## Verdict: KEEP, opt-in

"Knowing when you don't know" is core to an epistemic system, and this is the cheapest machinery that provides it. Costs are contained:

- Opt-in per claim (`set_interval`); the point-credence path is untouched.
- Separate bitemporal table; no schema disruption to claims.
- Dempster's high-conflict misbehavior is handled by **refusal**: K ≥ 0.99 emits `interval_refused` and keeps the old interval instead of producing nonsense (Zadeh's paradox, documented in the research).

## API

`set_interval` / `get_interval` / `ignorance` (= Pl − Bel) / `combine_interval` (Dempster's rule on the binary frame). All interval changes are events (`interval_set`, `interval_combined`, `interval_refused`).

## Open (not decided here)

- Whether the abstention policy should live in the ledger core or in the calling agent (currently the ledger exposes ignorance; the policy is the caller's).
- Extending beyond the binary frame (deferred; the binary case covers the abstention use-case).
