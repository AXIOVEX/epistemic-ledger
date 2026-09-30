# Design Memo 01 — Record schema and scoring calculus

**Status:** draft for review, 2026-09-30. Decisions marked **DECIDED** are the author's recommendation; Tristen rules. Builds on the framing paper (`PAPER.md`) and the eight research threads (`research/`).

## 1. Record schema

**DECIDED: both — events as the write model, bitemporal tuples as the read model.**

"Tuples vs. events" is a false choice. The append-only event log is the ground truth; bitemporal claim records are materialized projections of that log. This is the XTDB/Datomic shape: log-first, index-second.

### 1.1 Events (write model, immutable)

Every event carries: event id, transaction time (ingest timestamp, system-assigned, never trusted from the writer), actor, and a payload of one of:

- `assert(claim_id, statement, valid_from, valid_to, initial_score)` — a new conclusion enters the ledger.
- `support(claim_id, supports_id, kind)` — records *why* a claim is held. `kind` ∈ {`deductive`, `evidential`, `llm-generated`, `human-asserted`}.
- `retract_support(...)` — a justification is withdrawn. The claim survives while one complete justification remains (the TMS rule).
- `supersede(old_claim_id, new_claim_id)` — correction. The old claim's transaction-time interval closes; nothing is deleted.
- `score_revision(claim_id, old_score, new_score, triggering_event_id)` — every score move is itself an event with a cause pointer.

### 1.2 Claims (read model, bitemporal)

Derived by replay: claim id, statement, valid-time interval (when it held in the world), transaction-time interval (when the ledger believed it), current score, score-kind, status (`active`/`superseded`), and its live support set.

### 1.3 Why this split

- The log gives "what changed between T1 and T2" for free (filter by transaction time).
- The bitemporal projection gives "what did we believe at T" for free (`AS OF` semantics).
- Corrections are compensating events, never mutations — the audit trail is total.

## 2. Scoring calculus

**DECIDED: single credences as the native type; Jeffrey conditionalization for uncertain evidence; Dempster–Shafer intervals available per-claim where ignorance must be explicit.**

- **Base rule:** sequential Bayesian updating. Today's posterior is tomorrow's prior. Every `score_revision` event records the likelihood that produced it, so any score is auditable back to its evidence.
- **Uncertain incoming evidence** — the common case, including every LLM-produced input — goes through **Jeffrey kinematics**, not naive conditioning. Evidence at credence 0.7 moves the posterior 70% of the way; it does not get rounded to fact.
- **D–S belief/plausibility intervals** are opt-in per claim, for cases where "we don't know" must be represented rather than smeared across hypotheses (e.g., genuinely conflicting sources). Not the default: mass functions blow up, and Dempster's rule misbehaves under high conflict.
- **Imprecise probabilities** (sets of distributions): deferred. Too heavy for v0.1; revisit if calibration fails.

### 2.1 Calibration discipline (non-negotiable)

LLM verbalized confidences are poorly calibrated out of the box. Therefore:

- Scores are machine-maintained posteriors from explicit likelihoods, never raw LLM vibes.
- LLM outputs enter as *evidence events with attached credence*, never as deductive justifications (see §4).
- Every claim's score is scored itself: Brier score of credences against observed outcomes, tracked in the ledger. See kill criterion §6.4.

## 3. Support edges and the revisit loop

- Each claim's support set is the justification graph (the TMS durable pattern): track *why* each belief is held; propagate retraction through the support relation.
- **Revisit loop:** new fact → find claims whose support set intersects the fact → recompute their scores → propagate to dependents → halt when score deltas fall below the per-claim materiality threshold (early cutoff, the incremental-recomputation pattern).
- **Contradiction handling:** on conflict, epistemic entrenchment decides what gives way — the least-entrenched claim in the support closure is revised first (AGM's "what to give up" rule, implemented as an entrenchment ordering maintained per claim).

## 4. LLM-produced conclusions

Frontier LLMs measurably violate AGM postulates under iterated revision — so the ledger never treats LLM output as logical derivation.

- LLM claims enter as `llm-generated` support edges carrying: model id, prompt hash, and the model's self-reported credence (flagged provisional).
- They participate in retraction propagation like any other support, but revision never treats them as theorems: a conflict between an LLM claim and a deductive/evidential claim resolves against the LLM claim unless its entrenchment says otherwise.
- **Offline consolidation** (the Letta lesson): LLM-generated subgraphs get a periodic consolidation pass that re-derives or prunes them, rather than trusting incremental self-edits.

## 5. Materiality threshold — placement and tuning

Three-layer ladder (from the trigger research):

1. **Dirty-flagging:** any new fact marks its support-closure dirty. Sound, over-invalidates. Always on.
2. **Precise invalidation:** recompute only when an input's *value* actually changed past epsilon. The epsilon lives per-claim; default 0.01 score-delta.
3. **Materiality:** even a real change may not warrant action. Threshold per-claim, default tuned so a review cycle surfaces ~8–15 flags (the empirical heuristic from the research); re-tuned as scale changes. Claims above a criticality tier skip layer 3 — some conclusions always get revisited.

## 6. The ledger's own kill criteria

The design is failing if any of these hold over a sustained window:

1. **Missed triggers** — facts arrive that *should* have revisited claims (judged by a held-out audit sample) but didn't. Trigger recall below bar.
2. **Churn** — scores oscillate without converging on stable evidence. The calculus is unstable.
3. **Support-graph blowup** — justification fan-out grows superlinearly per claim (the ATMS label-explosion warning). Tracking costs more than the conclusions are worth.
4. **Miscalibration** — Brier score of claim credences vs. outcomes stays flat or worsens. The scores are theater.
5. **Override rate** — human reviewers hand-correct scores above a set rate. The system isn't earning its keep.

Any one sustained = redesign the failing layer. Two or more = the architecture is wrong; kill it.

## 7. Query language (v0.1)

- `BELIEVED_AT(T)` — bitemporal projection scoped to transaction time T.
- `CHANGED(T1, T2)` — event-log filter; returns assertions, supersessions, and score revisions with causes.
- `DEPENDS_ON(F)` — reverse traversal of support edges from fact F; returns the full revisit closure.
- `WHY(claim_id)` — the claim's live support set with scores and kinds. The audit view.

## 8. Prototype scope (v0.1)

Append-only JSONL event log; SQLite bitemporal claim table; one support-edge type set; one revisit loop with Jeffrey updates; one materiality rule; the four queries above. No distributed anything. Success = the five kill criteria are instrumented from day one, even if the bars are guesses.

## 9. Open (not decided here)

- Exact likelihood-elicitation procedure for human-entered evidence.
- Entrenchment ordering maintenance: manual tiers vs. learned.
- Whether D–S intervals earn their keep or get cut in v0.2.
