# Design Memo 10 — Governance hardening: escalation + signed verdicts

**Date:** 2026-10-02. **Status:** decided; implemented in
`prototype/ledger.py` + `prototype/ed25519.py` (v0.9). Closes two
items deferred by Design Memo 06.

## 1. Escalation workflow for held contradictions

v0.6 held non-owner challenges to axiomatic claims, but the hold
was a dead end: the only exit was the owner filing a fresh
declaration. Now the hold is a queue with a verdict:

`escalate_contradiction(held_id, decision, writer=...)`,
decision ∈ {release, dismiss}:

- **Owner-only.** The writer's live tier must be `owner`; anything
  else raises PermissionError. (Unlike declaration, escalation is a
  verdict, so it fails loudly instead of holding politely.)
- **release** emits a normal `contradiction` event for the pair
  (payload carries `released_from`, the held event's recorded
  p_loser_given_winner, and the escalator), so the released item
  flows into `open_contradictions()` / `resolve_contradiction`
  unchanged, and drops off `held_contradictions()` by the existing
  pair-matching rule.
- **dismiss** emits `contradiction_dismissed`; the held item drops
  off `held_contradictions()` and never enters the open queue.
- Escalating an id that is not currently held raises KeyError.
  The held payload now records p_loser_given_winner so a release
  preserves the challenger's elicited cross-likelihood.

## 2. Signed verdicts (ed25519)

Verdicts — contradiction resolutions and escalations — are the
ledger's acts of authority. A writer may register an ed25519
public key (`register_writer(..., public_key=<hex>)`, bitemporal
like tiers; re-registering without a key preserves the current
one). Rule:

> If the acting writer has a registered public key, a verdict
> action by that writer requires a valid signature over the
> canonical verdict message; missing or invalid raises
> PermissionError and nothing is emitted. Writers without keys act
> unsigned, exactly as before (back-compatible).

Canonical message (exact bytes signed, also stored in the verdict
event's payload as `signed_message`):

```
axiovex-ledger/verdict/v1|action=<resolve|escalate>|id=<target event id>|writer=<writer id>[|decision=<release|dismiss>]
```

The verdict event payload records `signer` and `signature` (hex).
`verify_verdict_signatures()` audits the log: every event
carrying a signature is re-verified against the signer's *current*
registered key; returns counts plus the invalid event ids. Caveat
(recorded, accepted for v1): key rotation invalidates older
verdicts under audit — audit answers "does the current key vouch
for this?", not a historical key-chain proof.

Private keys never enter the ledger: callers hold seeds and sign
externally via `Ledger.verdict_message(...)` +
`ed25519.sign(seed, msg)`. The implementation is the RFC 8032
reference algorithm vendored in `prototype/ed25519.py` (stdlib
hashlib only — the prototype stays zero-dependency), validated
against the RFC 8032 §7.1 test vectors in the test suite.

## Deferred still

Named-graph partitions and a post-state predicate language
(Design Memo 06) remain future work; neither is load-bearing for
the validation story yet.
