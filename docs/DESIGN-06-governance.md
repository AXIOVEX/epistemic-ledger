# Design Memo 06 — Ledger governance (Quipu-informed)

**Date:** 2026-10-01. **Status:** decided; implemented in `prototype/ledger.py` (v0.6).

## What Quipu contributes

Read: Brown, "Quipu: A Governed Bitemporal Knowledge Graph Store,"
arXiv:2608.16813 (Aug 2026). Relevant mechanisms for the ledger:

1. **Gated writes** — no fact enters except through a gate whose predicates
   evaluate the pending *post-state* (GS1). Pre-state checks pass writes
   that are valid alone and invalid in combination.
2. **Verdict permanence** — every gate decision persists as a signed,
   time-indexed fact surviving the rollback of the write it judges (GS2).
3. **Partitioned authority** — authority attaches to partitions; delegation
   only narrows; composition never widens (GS3/GS4). Flat trust lets one
   query launder a quarantined source's claims into attested prestige.
4. **Σ as facts** — the governance specification, trace, and verdicts live
   in the store they govern; the audit is a query (GS5). Rules themselves
   are bitemporal (GS6): "what was allowed at T" is answerable.

## Adaptation to the belief ledger

The ledger's contested write is the **contradiction declaration**, not the
assertion: assertions are cheap and revisable (that's the point of the
ledger); contradictions trigger forced revision of the loser. So:

- **Writers** are registered with trust tiers
  (`owner` / `contributor` / `provisional`), bitemporal.
- **Assert gate (D3 inversion):** a writer's tier sets the default
  entrenchment of their claims — owner 0.75, contributor 0.5, provisional
  0.25; unregistered writer 0.25 (unknown identity: least trust); no writer
  0.5 (system default, backward compatible). Explicit entrenchment always
  overrides; the writer name is recorded on the claim and carried across
  bitemporal versions for audit. Trust is no longer flat: low-trust
  writers' claims start easier to dislodge.
- **Contradiction gate (GS1/GS3):** a non-owner declaring a contradiction
  against an *axiomatic* (entrenchment 1.0) claim has the declaration
  **held** — it does not enter the open queue. Challenging axioms requires
  owner authority. The hold is a verdict: `contradiction_held` event with
  policy, target, outcome, and attribution.
- **Verdict permanence (GS2):** the ledger's append-only event log already
  gives this — the `contradiction_held` verdict is an event, never mutated.
- **Σ as facts (GS5):** the active policy set lives in a `policies` table
  (name, description, version, bitemporal). `audit_policy(name, t)` answers
  "what rule was in force at T" (GS6).

## Deliberately deferred

- **Signatures** (GS2's ed25519): no key infrastructure in the prototype;
  attribution is recorded, not cryptographically sealed. Required before
  any multi-party deployment.
- **Named-graph partitions**: the ledger has one belief space; partitions
  (per-agent, per-domain views with non-widening composition) are future.
- **Post-state predicate language**: the current gates are two built-ins.
  A general claim language over the pending post-state (Quipu's SPARQL
  asks) is the natural next step.
- **Escalation/require-approval**: held contradictions have no approval
  workflow yet — an owner re-declares to proceed. The hold verdict names
  the remediation (owner review), which is the agent-retry loop's input.
