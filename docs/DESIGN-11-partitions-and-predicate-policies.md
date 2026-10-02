# Design Memo 11 — Partitions and predicate policies (v0.10)

**Date:** 2026-10-02. **Status:** decided; implemented in
`prototype/ledger.py` (v0.10). Closes the two deferrals carried by
Design Memos 06 and 10.

## A. Named-graph partitions (Quipu GS3/GS4)

Quipu's warning: flat trust lets one query launder a quarantined
source's claims into attested prestige. GS3/GS4 answer: authority
attaches to partitions; delegation only narrows; **composition never
widens**.

Ledger adaptation — a partition is an *authority domain*, not an
access-control list (fine-grained per-graph writer ACLs remain future
work, and this memo does not pretend otherwise):

- **Graphs are bitemporal facts.** `register_graph(name, ceiling)`
  records a graph with an authority **ceiling** in [0, 1]: the maximum
  entrenchment any claim in it can effectively wield.
  `audit_graph(name, t)` answers "what ceiling was in force at T."
- **Assignment is bitemporal.** `assign_graph(claim_id, graph)`;
  unassigned claims live in the implicit graph `public`, ceiling 1.0
  (no cap) — pre-v0.10 ledgers behave identically.
- **Non-widening composition, enforced at read time.**
  `effective_entrenchment(claim)` = min(stored entrenchment,
  ceiling(own graph), ceilings of the graphs of its *direct
  supporters*). A claim resting on a quarantined partition's claims
  inherits the quarantine cap for every decision entrenchment drives,
  however high its stored value sits. Composition is one-step and
  local; deeper ancestry composes through each intermediate claim's
  own effective value when that claim is itself judged.
- **Non-destructive.** The cap never rewrites the stored value.
  Retracting the cross-graph support or reassigning the claim lifts
  the cap; every step is an auditable event.
- **Wired where entrenchment decides:** the contradiction gate's
  axiomatic test (a stored-1.0 claim inside a capped graph does *not*
  get axiom protection — quarantine strips prestige, exactly the
  laundering direction GS3 warns about) and
  `resolve_contradiction`'s winner/loser ordering and tie test.

## B. Post-state predicate policies (Quipu GS1/GS5/GS6)

GS1: gates evaluate predicates over the pending *post-state*, because
pre-state checks pass writes that are valid alone and invalid in
combination. Through v0.9 the ledger's gates were two built-ins
compiled into code, with policies stored as prose. Now the rules are
data:

- **Rule shape.** A policy may carry a rule:
  `{"action": <gated action>, "effect": "hold"|"deny",
  "when": <predicate>}`. Predicates are a deliberately small language
  — no code evaluation, ever: leaves
  `{"field": F, "op": OP, "value": V}` with OP in
  `==, !=, <, <=, >, >=, in, not_in`; nodes `{"all": [...]}`,
  `{"any": [...]}`, `{"not": pred}`. Rules are validated recursively
  at registration (malformed → ValueError); a missing context field
  makes a leaf false. `hold` is only valid for
  `declare_contradiction` — it means "park for an owner verdict," and
  the other gated actions *are* verdicts, so holding them is refused
  at registration rather than given a pretend semantics.
- **Post-state contexts.** Each gated action builds a context of the
  state the write *would* produce — for `declare_contradiction`, the
  declarer's tier and the target's *effective* entrenchment; for
  `resolve_contradiction`, both parties' effective entrenchments and
  the resolver's tier; for `escalate_contradiction`, the escalator's
  tier and decision — and every live policy whose action matches is
  evaluated against it. `deny` beats `hold`.
- **Verdict permanence (GS2).** A deny emits a `policy_denied` event
  and raises PermissionError before any mutation; a hold follows the
  existing `contradiction_held` path, now naming the policy that fired.
- **The built-in is now data.** The default policy
  `challenge-axiom-requires-owner` is registered at version 2 with its
  rule spelled out (`target_entrenchment >= 1.0 AND writer_tier !=
  "owner"` → hold). Legacy databases whose live default policy carries
  no rule fall back to the compiled-in equivalent predicate, so the
  gate's semantics do not depend on registration history.
- **Σ as facts, still.** Rules live in the `policies` table beside
  their prose, bitemporal; `audit_policy(name, t)` returns the rule in
  force at T along with the description.

Deliberately not done: gating `assert_claim`/`ingest_evidence` (the
tier-default entrenchment already soft-gates assertion, and hard
gates on the evidence path would fight the revisit loop's design);
per-graph writer ACLs; a predicate surface beyond comparisons and
boolean composition (no arithmetic, no quantifiers — the contexts are
flat by design).
