# Epistemic Ledger

A living epistemic ledger: an append-only database where every
conclusion carries a fluid certainty score, and new facts automatically
trigger re-evaluation of the conclusions — and their dependents — that
they affect, instead of any judgment ever being final.

Databases today have no built-in way to keep challenging the data, to
know how true any of it is, or to update it as evidence comes in. A
record is written, and from then on it sits — unexamined, silently
going stale while decisions compound on top of it. The ledger is an
attempt to fix that.

## The four properties

1. **Append-only records.** Conclusions are never changed or deleted.
   A correction is a new record that supersedes the old one; the full
   history of what was believed, and when, stays queryable.
2. **Fluid certainty scores.** Every conclusion carries a score that
   moves as evidence accumulates — today's result is tomorrow's
   starting point — instead of a one-time yes-or-no verdict.
3. **Dependency-tracked revisits.** Each conclusion records *why* it
   is held. When a new fact arrives, the change spreads along the
   dependency graph and re-evaluates exactly the conclusions it
   touches, plus their dependents.
4. **A trigger discipline.** Not every new fact warrants a revisit. A
   layered rule decides when recomputation is required, so the system
   neither goes stale nor churns.

## Start here

- [Getting started](getting-started.md) — install the package and run
  your first ledger in a few minutes.
- [Concepts](concepts.md) — the ideas in plain language: records,
  scores, revisits, and the trigger discipline.
- [The framing paper](PAPER.md) — the full research framing, with the
  measured results and their reports.
- [API reference](api.md) — the Python API, generated from the code.

## Install

```bash
pip install epistemic-ledger
```

Standard library only. No dependencies, no network at runtime.

## License

The code is under the MIT License. The framing paper, design memos,
and research documents on this site remain all rights reserved,
© 2026 Axiovex Systems, LLC.
