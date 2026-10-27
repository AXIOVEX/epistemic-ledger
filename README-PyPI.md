# Epistemic Ledger

A living epistemic ledger: an append-only database where every
conclusion carries a fluid certainty score, and new facts automatically
trigger re-evaluation of the conclusions — and their dependents — that
they affect, instead of any judgment ever being final.

```bash
pip install epistemic-ledger
```

```python
from epistemic_ledger import Ledger

ledger = Ledger("my-ledger")
claim = ledger.assert_claim("the bridge design is safe", 0.60)
fact = ledger.ingest_evidence("load test passed", 0.90)["fact_id"]
ledger.add_support(claim, fact, "evidential", p_given=0.95, p_given_not=0.30)
print(ledger.get_score(claim))  # the score moved; the history kept both
```

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
4. **A trigger discipline.** Not every new fact warrants a revisit.
   A layered rule — dirty-flagging, precise invalidation, then a
   materiality threshold — decides when recomputation is required.

## What is inside

- An event-sourced, bitemporal store (append-only JSONL event log as
  the write model, SQLite bitemporal tables as the read model).
- A revisit loop using Jeffrey conditionalization for uncertain
  evidence, with an early cutoff and materiality flags.
- Joint likelihoods (noisy-AND / noisy-OR), Dempster–Shafer belief
  intervals where ignorance must be explicit, and automatic
  contradiction detection with entrenchment-ordered resolution.
- Governance: writer trust tiers, signed verdicts (Ed25519), named
  graph authority ceilings, and predicate policies — all stored as
  bitemporal facts in the ledger they govern.
- A hardened single-writer store with replay verification
  (`epistemic-ledger verify <dir>`).
- The five kill criteria the design set for itself, instrumented from
  day one (`epistemic-ledger kill-metrics <dir>`).
- An offline LLM consolidation pass and caller-owned abstention
  policies.

Standard library only. No dependencies, no network at runtime.

## Command line

```bash
epistemic-ledger demo                      # end-to-end scenario
epistemic-ledger verify path/to/ledger     # integrity check
epistemic-ledger kill-metrics path/to/ledger
```

## Documentation

Full documentation — the framing paper, the design memos, the measured
results, and the API reference — is at
https://epistemic-ledger.readthedocs.io/ and in the GitHub repository:
https://github.com/AXIOVEX/epistemic-ledger

## License

The code is under the MIT License (see `LICENSE` in the repository).
The framing paper, design memos, and research documents in `docs/`
remain all rights reserved, © 2026 Axiovex Systems, LLC (see
`LICENSE-DOCS.txt` in the repository).
