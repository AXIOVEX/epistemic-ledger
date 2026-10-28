# DESIGN-14 — Verified Writes

Status: approved for implementation by the owner's fleet standard of
2026-10-28 ("Verified writes + no silent degraded delivery — ALL
PROJECTS", `~/AGENTS.md`). This memo applies that standard to the
ledger's own write paths. It changes no formats, no APIs, and no
scoring behavior; it changes what a write must prove before the
ledger calls it committed.

## 1. Why

An append-only ledger whose writes can silently land short, empty,
or corrupted is a contradiction. The failure mode is not
hypothetical: the development environment for this project has an
intermittent platform defect (filed 2026-10-27 as `vm-file-writes`,
still open) under which writes intermittently fail with EPERM — and,
worst, a write can report success while the file on disk is empty
or partial. `flush` + `fsync` do not detect this: they report on
what the operating system accepted, not on what can be read back.

The rule this memo implements, verbatim from the fleet standard:
**every record write is read back and verified before anything
builds on it; a partial or empty record never stands as committed;
a failed state write fails the run closed (loudly).**

## 2. Audit of the 0.13.0 write paths

Every file write in the package was audited at 0.13.0
(main `26d43e52`). The write surface is small: the Python engine,
the migration tool, and the Rust core. The CLI, the query language,
and the MCP server write nothing but stdout.

Fragile — retrofitted by this memo:

- **F1. Python event append** (`ledger.py::_emit`). The event log
  is ground truth; every store mutation emits its event here first,
  then updates the projection. The append did `write + flush +
  fsync` with no read-back. A silently short or empty landing
  leaves the projection claiming state the log does not hold,
  while the caller is told the write succeeded.
- **F2. Migration map** (`migrate.py`). `migration-map.json` was
  written with a bare `open(..., "w")` + `json.dump` — no fsync,
  no read-back. The map is the only record of which legacy event
  each new sequence number came from; losing it silently breaks
  the migration's audit trail.
- **F3. Rust append** (`store.rs::append`). `write_all + sync_all`
  with no read-back. Detection existed, but only at the *next*
  open, which truncates a damaged tail — meaning a record the
  caller was told is committed could later vanish. Detection
  after the fact is not verification before reliance.
- **F4. Rust torn-tail repair** (`store.rs::open`). The repair
  truncates and fsyncs but never confirms the resulting length.
- **F5. Snapshot/restore residue** (`snapshot.rs`). Snapshot and
  restore writes were already verified before success is returned
  (a finished bundle is fully re-verified; a restored store is
  re-opened and its head and count compared). But when a
  post-write check failed, the files the call had written stayed
  on disk: a failed restore left a partial store that then
  blocked any retry with "destination exists," and a failed
  snapshot left a bundle-shaped directory that was not a bundle.

Sound — deliberately unchanged, with the reasoning on record:

- **The SQLite projection.** It is derived state, held in
  transactions, cross-checked against the log by `verify_store`,
  and rebuildable exactly from the log (DESIGN-13 section 7,
  differential-tested). The record of truth is the log; that is
  where verification belongs. Corrupting the projection is
  detectable and repairable; corrupting the log undetected is
  neither — so the log is what this memo hardens.
- **Projection rebuild** (`rebuild_projection`). Already the
  standard's pattern: build aside, swap atomically, verify the
  result end to end, restore the original on failure.
- **Snapshot bundle contents.** Already verified from the bundle
  alone before `write_snapshot` returns (DESIGN-13 claim R2);
  restore verifies before writing and re-validates after.

## 3. Design

### 3.1 Verified append (both engines)

An append is committed only when the bytes read back from the log,
at the offset the record was appended at, are byte-identical to
the bytes written, and the file's length is exactly the pre-append
length plus the record length. On any mismatch the append:

1. truncates the log back to its pre-append length and fsyncs
   (the partial record never stands);
2. retries the whole append, up to 3 attempts in total;
3. raises a loud error if no attempt verifies — and if the
   rollback truncation itself fails, the error says so explicitly
   and names the store, because the tail must then be treated as
   torn (the Rust open-scan already repairs that case; the error
   is the caller's signal not to build on the store).

Sequence numbers, chain head, and in-memory state advance only
after a verified append. Callers (projection updates in Python;
`head_hash`/`next_seq` in Rust) already run after the append
returns, so no caller changes are needed.

### 3.2 Verified whole-file write (Python)

A vendored helper, `epistemic_ledger._verified.write_file_verified`,
implements the fleet pattern for whole files: write to a temp file
in the same directory, fsync, **read back and hash-verify the temp
file before it can replace anything**, atomic rename, fsync the
directory, read back and hash-verify the target. Bounded retries
(3 attempts, a fresh temp file each time); total failure raises
`VerifiedWriteError`. Empty content is refused. Used first for
`migration-map.json`; any future whole-file state write in the
package uses it too.

One deliberate divergence from the fleet tool
(`~/workspace/system/safe-write/`): the tool's retry ladder includes
a fresh-subprocess rung, which exists because an *operator process*
on the defective VM can become write-tainted for life. Library code
does not spawn subprocesses of itself; instead it fails closed with
a loud error, which the standard equally requires ("a failed state
write fails the run closed"). The pattern — temp, fsync, rename,
read-back hash — is identical, and this implementation additionally
verifies the temp file *before* the rename, so unverified content
never replaces a good target even momentarily.

### 3.3 Repair verification (Rust open)

After truncating a torn tail, `Store::open` confirms the file's
length equals the intended keep-length before returning a store;
a mismatch is an error, not a store that believes it repaired.

### 3.4 No residue on failure (Rust snapshots)

When a post-write check fails, `write_snapshot` removes the two
bundle files it wrote (it verified at entry that neither existed),
and `restore_snapshot` removes the destination log it wrote.
A failed call leaves the filesystem as it found it, and a retry is
never blocked by the previous attempt's remains.

### 3.5 Fault injection for tests

The claims below are discharged by fault-injection tests, which
require the defect to be reproducible on demand:

- Python: the unverified append primitive and the whole-file
  write primitive are separate seams; tests replace them with
  doubles that land half the bytes, zero bytes, or garbage —
  transiently (first attempt only) and persistently.
- Rust: two `#[cfg(test)]`-only hooks (compiled out of release
  builds) make the append write land truncated or zeroed, and
  make snapshot file writes land zeroed. The hooks alter the
  bytes actually written, so the production read-back and
  rollback code runs against a genuinely wrong file.

## 4. Claims

- **W1 — No unverified Python event stands.** Every event
  `_emit` returns from is present in `events.jsonl` byte-for-byte
  at the moment it returns. A short, empty, or corrupted landing
  is detected before return, rolled back, and either retried to a
  verified success or raised as an error; under a persistent
  fault the log is byte-identical to before the call.
  *Falsifier:* the fault-injection tests of section 3.5 — if any
  injected fault lets `_emit` return normally while the log lacks
  the exact event bytes, or a persistent fault changes the log at
  all, W1 falls.
- **W2 — No unverified Rust record stands.** Same property for
  `Store::append`: `next_seq` and the chain head advance only for
  records read back byte-identical from the log. After a failed
  append with a successful rollback, reopening the store reports
  zero torn bytes and the pre-append record count.
  *Falsifier:* the Rust fault-injection tests — a truncated or
  zeroed landing that returns `Ok`, advances the head, or leaves
  a torn tail after rollback defeats W2.
- **W3 — Whole-file state is never unverified.** A file written
  through `write_file_verified` holds exactly the intended bytes
  when the call returns, or the call raises and the target either
  does not exist or still holds its previous verified content.
  *Falsifier:* fault injection on the temp write — if corrupted
  content reaches the target, or a failed call leaves new content
  of any kind at the target, W3 falls.
- **W4 — Repairs are verified too.** `Store::open` returns a
  store after torn-tail repair only when the post-repair length
  is confirmed. *Falsifier:* the length-check unit test plus the
  existing torn-tail battery staying green; a repair path that
  returns success on an unconfirmed length defeats W4.
- **W5 — Failure leaves no residue.** A failed snapshot or
  restore removes exactly the files it wrote; the destination is
  as it was before the call and a retry can proceed.
  *Falsifier:* the zeroed-write snapshot tests — if a failed
  `write_snapshot` leaves bundle files, or a failed
  `restore_snapshot` leaves a destination log, W5 falls.
- **W6 — The budgets still hold.** Verified appends keep every
  DESIGN-13 section-8 budget (the read-back is one short read per
  record, measured against the fsync it follows).
  *Falsifier:* the Battery + budgets CI job, a required check —
  any budget breach on the merging commit defeats W6.

## 5. Honest scope

- Read-back verification detects the defect's observed modes —
  writes that land short, empty, or different as seen when
  re-read through the operating system. That is the same evidence
  the fleet standard relies on, and the mode this project's own
  incident history shows (the defect was caught by read-backs in
  production tooling). It is not a proof against a storage layer
  that lies identically to the write and to every later read; no
  in-guest check can be. External anchoring (DESIGN-13 section 1)
  remains the answer at that layer.
- Verification is per-write, at write time. It does not replace
  the chain: a write verified today can still be altered tomorrow,
  which is what hashes, signatures, checkpoints, and snapshots
  detect. The two mechanisms cover different moments and both
  stay.
- Ordering across the Python engine's two stores is unchanged
  from 0.13.0: some write methods update the projection before
  emitting (`add_support`, `register_writer`, `register_policy`),
  others emit first (`_set_score`, `record_decision`). A
  verified-append failure therefore surfaces as a loud error from
  a method whose projection update may already be committed —
  the same divergence a crash between the two writes has always
  produced, under the posture 0.13.0 already ships: the log is
  truth, `verify_store` detects divergence, and
  `rebuild_projection` repairs it. What changes is that the
  divergence is announced at the moment it happens instead of
  being discovered later — or never. Reordering every write
  method is a separate design question and is deliberately not
  smuggled into this memo.
- The Python log's reader (`_events`) still refuses a damaged
  log loudly rather than repairing it; repair of the Python
  format remains "restore from a verified source," unchanged
  from 0.13.0. This memo makes damage at write time detectable
  and rolled back, which is where the standard points.
