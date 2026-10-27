# Concepts

The ledger in plain language. The full design record is in the
[framing paper](PAPER.md) and [Design Memo 01](DESIGN-01-record-schema-scoring.md);
this page is the short version.

## Records: events and claims

Everything that happens is written as an **event** in an append-only
log: a claim was stated, a reason was recorded for it, evidence
arrived, a score moved, a claim was replaced by a corrected one. The
log is never edited. What you query day to day — the claims, their
current scores, their reasons — is a **projection** built from the
log, and it can be rebuilt or checked against the log at any time
(the `verify` command does exactly that).

Each claim carries two time axes (**bitemporal** records):

- **Valid time** — when the claim held in the world.
- **Transaction time** — when the ledger believed it.

That split is what makes retroactive correction honest: fix a fact
about last month and the ledger can still answer both "what do we
believe now about last month?" and "what did we believe at the time?"

## Scores: credences that move

A claim's score is a **credence** — a degree of belief between 0 and
1, maintained by the system rather than guessed fresh each time. When
evidence arrives, the score is updated with the standard Bayesian
rule, softened for the common case where the evidence itself is
uncertain: **Jeffrey conditionalization** moves the score partway,
by exactly the amount the evidence supports, instead of rounding the
evidence up to a fact. Every score move is an event with a cause, so
any number in the system can be audited back to the evidence that
produced it.

Where "we don't know" must be stated rather than averaged away, a
claim can also carry a **Dempster–Shafer interval**: a belief floor
and a plausibility ceiling, with the gap between them being the
ledger's explicit ignorance. Callers can build abstention policies on
that gap — the ledger exposes the ignorance; the caller, who knows
the stakes, decides when it is too wide to act on.

## Revisits: why dependency tracking matters

Each claim records its **support** — the claims and facts it rests
on. That graph is what makes revision cheap and precise: new evidence
marks its dependents, recomputes their scores, and spreads the change
onward, stopping when the remaining changes fall below a **materiality
threshold** (the early cutoff). Three layers, coarsest to finest,
decide whether a change warrants a revisit: dirty-flagging (something
changed), precise invalidation (the value actually moved), and
materiality (the move matters). The thresholds were tuned by
measurement; the reports are in the result list.

Related claims can also support a conclusion *together* — joint
likelihoods (noisy-AND and noisy-OR) handle "all of these together"
and "any of these" instead of forcing evidence into a chain.

## Contradictions and governance

When two claims conflict, the ledger does not flip a coin. Each claim
has an **entrenchment** — how costly it would be to give it up —
which can be set by tier (axiomatic, measured, inferred, provisional)
or learned from how well the claim's scores have predicted outcomes.
The less-entrenched side gives way; a tie goes to a human, and the
decision itself is recorded.

Deployments with more than one writer add governance, all stored as
facts inside the ledger itself: writer trust tiers that set default
entrenchment, signed verdicts (Ed25519) for sensitive decisions,
named-graph authority ceilings, and predicate policies that can deny
specific actions.

## The kill criteria

The design carries five ways it could be failing, instrumented in
code from the first version: missed triggers, score churn,
support-graph blowup, miscalibration (scores that do not predict
outcomes), and a high human override rate. Any one, sustained, means
the failing layer gets redesigned. Run them on any ledger with
`epistemic-ledger kill-metrics <dir>`.
