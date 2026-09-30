# Topic 4 — Event sourcing and append-only logs (notes)

Read 2026-09-30 via browser_search (index-level, not live-verified).

## Core mechanism
- Every state change is stored as an **immutable event** (a fact about what happened) in an **append-only event log**. Never update, never delete.
- Current state is **derived by replay**: state = left fold over the event stream. Read models / projections / materialized views are built by consuming events and can be regenerated at any time by replaying.
- **Retroactive correction:** the doctrine is "you can't change the past, but you can replay it." Errors are corrected by appending **compensating events** (accounting-style reversals), never by rewriting history — the reversal itself becomes part of the auditable record. Exceptional redaction/repair (legal/operational necessity, e.g., GDPR) uses a controlled, auditable **stream-rewrite / version migration**, after which every dependent projection must be rebuilt.
- Engineering rules: events carry full payload (never rely on current state); past-tense domain names (OrderCreated, not "Updated"); validate commands *before* append; optimistic concurrency via expected-version checks on the stream; idempotency via command IDs in metadata (version check ≠ idempotency); snapshotting for long streams (snapshot is stale the moment written — always load snapshot + subsequent events); transactional outbox for reliable publishing.
- Commonly combined with CQRS: append-only ingestion and query-optimized projections scale independently.

## Canonical references
1. Greg Young — popularized the pattern ("events represent facts, which you never edit; you correct mistakes by adding new events rather than rewriting history").
2. Fowler, "Event Sourcing," martinfowler.com, 2005.
3. Microsoft Azure Architecture Center, "Event Sourcing pattern" (docs/patterns/event-sourcing.md).
4. Chris Richardson (microservices patterns) — event sourcing for workflows with many transitions and strong invariants.

## Practical limitations
- Streams grow without bound → snapshots, stream closure on business boundaries, or redesign.
- Replay cost and schema evolution: old events must remain interpretable (event versioning/upcasting); "replay must not reapply today's command rules to yesterday's accepted decisions."
- Projections are eventually consistent; consumers see low-level events and may need integration events.
- A wrongly recorded event is permanent (compensated, still visible) — the audit trail is a feature until it is a liability (privacy/redaction).
- Append-only storage alone is not tamper-evidence; concurrency conflicts must be surfaced, not blind-retried.

## Sources
- https://github.com/microsoftdocs/architecture-center/blob/HEAD/docs/patterns/event-sourcing.md (compensating events for reversed changes; audit trail; replay into materialized views; CQRS combination)
- https://www.devx.com/technology/event-sourcing-explained-capturing-state-changes-at-scale/ (Fowler/Young/Richardson synthesis; facts never edited)
- https://github.com/itohnobue/orchestrator-opencode/blob/HEAD/.opencode/agents/event-sourcing-architect.md (immutable events, append-only streams, snapshotting, optimistic concurrency, transactional outbox)
- https://github.com/robsonkades/agent-skills/blob/HEAD/skills/event-sourcing/SKILL.md (compensate-with-new-facts rule; exceptional stream-rewrite must be controlled/auditable with projection rebuilds; version check ≠ idempotency; append-only ≠ tamper-evidence)
