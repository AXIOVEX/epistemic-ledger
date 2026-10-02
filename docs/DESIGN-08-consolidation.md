# Design Memo 08 — The LLM consolidation pass

**Date:** 2026-10-02. **Status:** decided; implemented in
`prototype/consolidation.py` (v0.7).

## Why

NEWSROOM-01 finding 1: heuristic contradiction detection is at its
ceiling. Score-opposition cannot tell contradiction from legitimate
disagreement (AND vs. OR over the same parents); interval-conflict
needed a caller-supplied topic filter to stop flagging unrelated
propositions. Both gaps are the same gap: **proposition identity** —
knowing what a claim is *about* — which requires reading the
statements. That is what an LLM is for, and it is the piece Design
Memo 02 deferred ("probably via the LLM-consolidation pass").

## Shape: offline pass, outside the kernel

Following the Letta sleep-time pattern (separate asynchronous
memory-management agent; the primary loop never edits core memory):

- The deterministic kernel (Ledger) stays deterministic. The
  consolidator is a **client** of the ledger, run on demand / on a
  schedule, never inside the revisit loop.
- It reads live claims (statement, score, entrenchment, topic) and
  asks the LLM for three relation types:
  - `contradicts` — same proposition-space, mutually exclusive.
  - `same` — same proposition (paraphrase/duplicate).
  - `supports` — A, if true, is evidence for B.
- Per Design Memo 01, LLM output is **provisional evidence, never
  deductive justification**. Concretely:
  - `contradicts` → declared through the normal
    `declare_contradiction` path (actor="consolidator", auto=True,
    signal="llm-consolidation") — the governance gate still applies,
    and resolution still goes through entrenchment/humans.
  - `same` → topics assigned (`assign_topic`), making proposition
    identity first-class ledger data that the heuristic detector's
    `topic_of` can consume.
  - `supports` → **reported, not applied**. Restructuring the support
    graph on an LLM's say-so is a step too far for v1; the proposals
    are advisory for a human/agent review.

## Topics as ledger data

`claim_topics` is bitemporal. `assign_topic(claim_id, topic)` /
`get_topic(claim_id)`. The consolidator assigns; humans can override;
the heuristic detector consumes via `topic_of=ledger.get_topic`.

## Cost discipline

Every call's token usage is priced from the live OpenRouter catalog
and accumulated; the consolidator refuses to run past a hard cap
(default **$5** for this work item, set by Tristen 2026-10-02).
Model default: Claude Sonnet 4.5 (proposition understanding is the
quality bottleneck); Haiku 4.5 measured as the cheap alternative.

## Validation

Two measurements (docs/CONSOLIDATION-01.md):
1. **Corpus**: hand-written claims with planted paraphrase /
   contradiction / unrelated relationships → LLM precision & recall
   on text alone.
2. **Newsroom head-to-head**: same populated ledger, three detectors
   (heuristic, heuristic+topic, LLM) → genuine recall and false
   positives, incl. the (D1,D2) trap the heuristic cannot pass.
