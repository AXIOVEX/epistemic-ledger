# Epistemic Ledger

A living epistemic ledger: an append-only database where every
conclusion carries a fluid certainty score, and new facts automatically
trigger re-evaluation of the conclusions — and their dependents — that
they affect, instead of any judgment ever being final.

```bash
pip install epistemic-ledger
```

On Linux, macOS, and Windows the install brings a compiled Rust
core with it (the chained, signed store below); everywhere else
the same package works in pure Python with the functionality
noted as core-backed unavailable.

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
- The five kill criteria the design set for itself, instrumented from
  day one (`epistemic-ledger kill-metrics <dir>`).
- An offline LLM consolidation pass and caller-owned abstention
  policies.

## The chained store (compiled core)

- A hash-chained, Ed25519-signed append-only store with
  RFC 9162 Merkle checkpoints, a single-writer lock, and torn-tail
  recovery at open — middle damage fails loudly, never silently.
- Verified writes: every append is read back and checked before it
  is acknowledged, on both the Rust and Python paths.
- Anchoring: signed tree heads with inclusion and consistency
  proofs, plus a pure-Python standalone verifier — a reader with
  no trust in this package (or in the writer) can check a store's
  history against a pinned tree head.
- Tenant partitions and key governance: one chained store per
  tenant, with key enrollment and revocation recorded in the
  chain itself and a governed verification mode that rejects
  records signed outside a key's window.
- Commitments and erasure: identified payloads stay out of the
  chain as per-tenant keyed HMAC commitments; an erasure record
  attests the act while the chain — and its proofs — still
  verifies in full.
- Provenance export to W3C PROV (JSON), byte-for-byte
  deterministic for a given chain.
- Legacy stores migrate with attestation: the migration is
  itself the new chain's first record.
- A read-only query language, a command line, and a stdlib MCP
  server (12 tools).

Measured on CI runners (yours will differ): sustained appends
above 2,000 records/second with per-append fsync and read-back,
full-chain verification above 50,000 records/second, and a
1,000,000-record store that opens in about 2 seconds and
verifies end to end. A stress program — crash kill-point sweeps,
bit-rot sweeps, soak runs, fuzz campaigns, and resource floors —
runs on every pull request, nightly, and before each release;
its results are reported as what was proven and what was not.

The Python layer is standard library only. The platform wheels
add the compiled core; no runtime dependencies either way, and
no network at runtime.

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
