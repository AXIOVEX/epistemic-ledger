# Design Memo 12 — Hardening the store (v0.11)

**Date:** 2026-10-02. **Scope:** the prototype's store layer only.
Kernel semantics, scoring, governance, and every published
validation number are unchanged (suite 66/66; a post-hardening
modeled newsroom trial reproduces the archived seed-0 result
exactly — 0.140625 / 0.221875 / derived 0.1292 / 0.4542).

## What changed

1. **Single-writer lock.** A ledger directory is a single-writer
   store. `Ledger.__init__` now takes an exclusive advisory lock
   (`ledger.lock`, fcntl flock, non-blocking) before touching the
   database; a second opener gets a clear `RuntimeError` instead
   of two writers interleaving appends and projection updates.
   `close()` (and the context-manager protocol) releases it;
   process exit releases it automatically. Unix-only — on platforms
   without fcntl the lock is unenforced and this memo is the
   notice. Every existing flow opens one ledger per directory, so
   nothing in the program's own tooling changes behavior.
2. **Durability of the ground truth.** `_emit` now flushes and
   fsyncs the event log on every append. The JSONL log is the
   write model — losing its tail to a crash would silently orphan
   projection state. At prototype event rates the cost is noise
   (the full test suite's runtime did not grow).
3. **`verify_store()`.** A read-only integrity audit: every log
   line parses with required fields; event ids are unique; every
   asserted claim has a live projection row whose score equals
   the claim's terminal log value (last `score_revision`
   `new_score`, or the assert `prior`). It returns a report and
   never raises on bad data — corruption is a finding, not an
   exception. Tests cover the clean case, a tampered projection,
   and a corrupted log.
4. **Packaging.** `prototype/pyproject.toml` declares the five
   kernel modules (`ledger`, `consolidation`, `policies`,
   `elicit`, `ed25519`) as an installable, dependency-free package
   (`axiovex-ledger` 0.11.0). Verified: pip-installed into a clean
   venv and exercised end-to-end. The validation scripts keep
   their sys.path imports; nothing moved.

## Measured envelope (scale smoke, this VM class)

10,000 claims / 200 hub facts / 25,832 events
(`prototype/validation/scale_smoke.py`): build 3.2 s; one hub-fact
revisit 0.00 s (build_ledger facts have 1–5 direct dependents —
the smoke measures store mechanics, not adversarial fan-out);
`believed_at` over 10,201 live claims 0.05 s; `verify_store`
0.4 s, clean. An order of magnitude past every validation
workload (which peak at 600 claims), with no code path straining.

## Deliberately not done

- **No multi-writer support.** Concurrent writers would need
  transaction discipline around emit+project; the lock makes the
  actual contract explicit instead. A future multi-writer design
  is a new memo, not a patch.
- **No WAL mode.** SQLite's rollback journal plus the fsync'd log
  is sufficient at this scale, and WAL sidecar files complicate
  the copy-a-directory workflows the tooling relies on.
- **No access control.** Unchanged from Memo 11: partitions are
  authority ceilings, not security boundaries. Hardening the
  store is not securing a deployment, and this memo does not
  claim otherwise.
