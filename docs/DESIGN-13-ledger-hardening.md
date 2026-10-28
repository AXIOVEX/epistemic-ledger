# DESIGN-13 — Ledger hardening: cryptographic tamper evidence, a Rust engine, impact analysis, and the query/interface layer

Status: approved by Tristen 2026-10-27 (plan, crypto, Rust engine, and
the layered interface each approved the same evening). This memo is
the spec for the 0.13.0 line. Every requirement below is stated as a
claim with a falsifier; code ships only against claims, and a claim is
described as proven only when its acceptance test passes on the
shipped artifact.

## Why this memo exists

Version 0.12.0 packages the research prototype honestly, but an audit
of the shipped code (2026-10-27) established four gaps between what
the ledger is described as and what the code guarantees:

1. The event log has no cryptographic chaining. `verify_store`
   checks that the live projection agrees with the log; a rewrite of
   both together would pass. Tamper evidence is therefore claimed by
   the design memos but not provided by the code.
2. Claims can be traced (`why`, `depends_on`, a dependents
   traversal), but there is no impact query: "if this claim falls,
   what else moves, and which decisions were made on top of it?" has
   no answer a caller can ask for.
3. The store is a single local file set. There is no snapshot,
   export, or restore story.
4. Nothing is measured. There are no benchmarks, no crash or
   corruption drills, and no health reporting, so "fast and
   reliable" is an adjective, not a fact.

This memo closes those four gaps and adds the interface layer
approved alongside it.

## Decisions recorded

- D1. The storage and scoring engine is rewritten in **Rust**, with
  **Python bindings** (PyO3, built with maturin) that preserve the
  0.12.0 Python API. The pure-Python implementation remains in the
  package as the reference implementation and differential-test
  oracle; it is not the default engine once the Rust engine reaches
  parity.
- D2. Tamper evidence is cryptographic: a **hash chain** over every
  event (SHA-256, each event committing to the previous event's
  hash), **Ed25519-signed appends** for identified writers, and
  periodic **Merkle checkpoints** over chain segments so a segment
  can be verified without replaying the whole log.
- D3. The interface is layered: the Python API at the core, a small
  read-only **query language (LQL)** over it, and two faces — an
  **MCP server** for agents and the **CLI** for people. Writes never
  pass through the query language.
- D4. Redundancy means: checksummed records, verified snapshots, and
  a restore path that is drilled in CI — not a claim about any
  particular deployment's replication, which stays the operator's
  responsibility and is documented as such.
- D5. Stores written by 0.12.0 (events.jsonl + ledger.db) must
  migrate: an import path reads the old log, rebuilds it as a
  chained log, and the migrated store must verify end to end.

## Architecture at a glance

- `epistemic-ledger-core` (Rust crate): the storage engine, the
  chain and signature verification, the scoring/revisit engine, the
  impact traversal, snapshots, health checks, and recovery.
- `epistemic_ledger` (Python): the 0.12.0 public API, re-pointed at
  the Rust core through PyO3 bindings; the pure-Python engine stays
  importable as `epistemic_ledger.pyengine` for reference and
  differential testing.
- `epistemic-ledger` CLI: gains `impact`, `query`, `snapshot`,
  `restore`, `health`, and `verify --deep` commands over the same
  core.
- MCP server (`epistemic-ledger-mcp` entry point): typed tools over
  the same core (section 6).

## 1. Cryptographic tamper evidence

### 1.1 Record and chain format

Each event is stored as a record:

```
seq        monotonically increasing integer, starting at 1
t          timestamp (as today)
actor      writer identity (as today)
type       event type (as today)
payload    event payload (as today)
prev_hash  SHA-256 of the previous record's canonical encoding
           (the genesis record uses 32 zero bytes)
hash       SHA-256 of this record's canonical encoding, which
           includes prev_hash — so each hash commits to the entire
           history before it
sig        Ed25519 signature over `hash` by the writer's key, when
           the writer has a registered key; absent only for the
           reserved `system` actor during migration
checksum   CRC32C of the record bytes as stored (see 2.3)
```

The canonical encoding is a deterministic byte serialization of
(seq, t, actor, type, payload, prev_hash) — field order fixed,
strings UTF-8, payload serialized with sorted keys and no optional
whitespace — specified exactly in the implementation's
`CHAIN-FORMAT.md`, with test vectors. Two independent encoders
(Rust core and the Python reference) must produce byte-identical
encodings for the same record; a shared vector file proves it.

Claim H1: altering any byte of any historical record, deleting a
record, inserting a record, or reordering records is detected by
verification, and verification names the first sequence number at
which the chain breaks.
Falsifier: a test battery mutates a real store each of those ways
(bit flips at randomized offsets, deletion, insertion, swap) and
verification must fail with the correct first-bad sequence number
in every case.

Claim H2: an event attributed to a registered writer verifies
against that writer's public key; a forged or re-attributed event
fails signature verification even if its chain hashes are
recomputed consistently.
Falsifier: the battery includes a full-chain rewrite with correct
hashes but wrong keys; verification must reject it on signature
grounds. This is the attack plain hash chaining cannot stop, and
the reason signatures are not optional for identified writers.

### 1.2 Merkle checkpoints

Every N events (default N = 1024, configurable), the engine writes
a checkpoint: the Merkle root over that segment's record hashes,
the segment's first and last sequence numbers, and the previous
checkpoint's root, itself chained and signed by the store's
checkpoint key. Checkpoints let a verifier check one segment
without the whole log, and give an external party a single short
value (the latest checkpoint root) to pin and compare — the
transparency-log pattern from Ledger Standard v1.

Claim H3: given only a checkpoint root and a segment, segment
verification succeeds for an untouched segment and fails for a
tampered one, without reading any other segment.
Falsifier: segment-level tests with tampering inside and outside
the segment under test; outside tampering must not affect the
inside verdict and vice versa.

Claim H4: verification is complete, not sampled. A full `verify`
walks every record and every checkpoint.
This does not establish that a store whose *entire* history was
replaced before its first checkpoint anchor — chain, signatures
with the real keys, and checkpoints — can be detected from the
store alone. It cannot; that is what external anchoring of
checkpoint roots is for, and anchoring integrations are out of
scope for 0.13.0 (the checkpoint root is exposed precisely so an
operator can anchor it elsewhere).

## 2. The Rust storage engine

### 2.1 Layout and write discipline

A store is a directory:

```
events.log     append-only chained records (the ground truth)
checkpoints/   checkpoint records, one file per checkpoint
index.db       SQLite projection (claims, edges, writers, scores),
               rebuildable from events.log at any time
ledger.lock    single-writer advisory lock (as DESIGN-12)
keys/          optional local key material references; private
               keys are never stored in the store directory by
               default — the engine takes key handles/paths
```

Write path: serialize the record, compute hash and signature,
append to `events.log`, fsync, then apply to the projection in the
same transaction discipline as today. The log remains ground
truth; the projection is always disposable and rebuildable.

Claim E1: a crash at any point in the write path leaves the store
either at the last complete record or recoverable to it by
truncating a torn tail — never with a partial record accepted as
valid, and never with the projection ahead of the log.
Falsifier: the adversarial battery (section 7) kills the process
at randomized points during append bursts and truncates the log
at randomized byte offsets; on reopen, the store must verify or
recover to a verifying state, and must never open silently wrong.

### 2.2 Single writer, many readers

The DESIGN-12 single-writer rule stands. Readers may open the
store read-only concurrently with the writer; read-only opens
take no lock and cannot mutate files.

Claim E2: a read-only opener can run full verification and any
query while a writer holds the lock, and cannot alter a single
byte of the store (checked by file hashes before and after in
tests).

### 2.3 Error detection and correction ("ECC")

Three layers, each with a distinct job:

- **Detection per record:** the CRC32C checksum catches torn or
  corrupted record bytes at read time and names the record.
- **Detection per history:** the hash chain (section 1) catches
  any rewrite, including one that fixes up checksums.
- **Correction by redundancy:** a corrupted segment is repaired
  from a verified snapshot or replica of the log: `recover`
  locates the first bad sequence number, truncates there, and
  replays the good copy's records from that point, re-verifying
  the chain across the seam. Correction never invents data — if
  no verified good copy exists, recovery stops at the truncation
  point and reports exactly what was lost.

Claim E3: with a verified snapshot present, any single-segment
corruption of `events.log` is recovered to a fully verifying
store whose live projection matches the uncorrupted original.
Falsifier: corruption drills corrupt each segment in turn and
diff the recovered projection against the original.
This does not establish survival of simultaneous corruption of
the log and all snapshots; redundancy depth is an operator
choice (D4), and the health report says how deep it currently is.

### 2.4 Health features

`health` (API, CLI, and MCP) reports, in plain values: store
format version, event count, last sequence number, latest
checkpoint root and its age in events, chain status from the last
verification (and when it ran), projection-vs-log agreement,
snapshot inventory with ages and verified status, lock state, and
any corruption or recovery events since the last clean report.
A background `scrub` operation re-verifies the chain segment by
segment and updates health state; it is incremental (checkpoint
by checkpoint) so it can run on large stores without a full pass.

Claim E4: after any drill in the adversarial battery, `health`
reflects the damage (or the recovery) accurately — no drill may
end with health reporting a clean store over a damaged one.

## 3. Impact analysis: what a challenge touches

### 3.1 Decisions as graph nodes

Today decisions appear as governance acts (verdicts, holds,
dismissals) recorded in the log. 0.13.0 makes them addressable
nodes in the dependency graph: a decision records the claims it
rested on (its basis set) at the moment it was taken, by explicit
reference, immutable thereafter. A claim's dependents then include
both derived claims and decisions, and a traversal answers the
question this whole product exists for: *if this claim falls,
what did we build on it?*

Existing governance acts migrate: their claim references become
basis sets where the act names them; acts that name no claims get
an empty basis set, honestly, not a reconstructed one.

### 3.2 The impact query

`impact(claim_id, mode)` with two modes:

- **Structural:** the transitive closure of dependents (derived
  claims and decisions), each with its graph distance and the
  shortest paths it was reached by.
- **Propagated:** additionally, the score movement each dependent
  would see if the claim's score were revised to a stated value
  (or challenged to zero), computed by the same revisit machinery
  that performs real revisions — run dry, changing nothing.

Amendment (2026-10-28, owner-approved): the original structural
semantics listed *every* simple path per node. Measured on the
section 8 reference graph, that output is intrinsically
unbounded on dense graphs (whole-graph closure: 426 ms against
the 100 ms budget, with the enumeration cap binding) — no
implementation of those semantics meets the budget. Structural
impact now lists the *shortest* paths (at most 100 per node) and
reports `path_count`, the exact number of shortest paths
(saturated at 10^15); listing fewer than the count flags
truncation exactly as the old cap did. Claim I1's brute-force
oracle is amended to match: distances and shortest-path sets,
exactly.

Claim I1: the structural closure returned by `impact` equals a
brute-force closure computed independently from the raw edge set
— exactly, on randomized graphs, including graphs with diamonds,
cycles broken by the derivation rules, and decision nodes.
Falsifier: property tests (Hypothesis) comparing the two on
generated graphs; any mismatch fails.

Claim I2: propagated impact scores equal the scores a real
revision to the same value produces, claim for claim.
Falsifier: property tests performing the dry run and then the
real revision on a copy of the store, diffing every score.
This does not establish that a decision in the blast radius was
*wrong* — only that it rested on the challenged claim. Judging
decisions stays with people; the ledger's job is to make sure
they are never surprised about what they were standing on.

### 3.3 Cost bounds

Impact is an interactive query, so it is bounded: callers may cap
depth and result size, the defaults are stated in the API docs,
and hitting a cap is reported in the result — never silently
truncated.

Claim I3: on the reference graph of section 8 (10,000 claims,
~40,000 edges), a full structural impact closure completes inside
the section 8 budget on CI hardware, and a capped query reports
its cap.

## 4. Redundancy: snapshots, export, restore

- `snapshot` writes a self-contained bundle: the chained log (or
  the segment range since the last snapshot, for incrementals),
  the checkpoint set, and a manifest whose hash covers the bundle.
  A snapshot is verifiable on its own, without the live store.
- `restore` builds a new store from a snapshot bundle alone,
  replays it, and verifies the full chain and checkpoint set
  before the store is allowed to open.
- Snapshots are the unit of backup, replication, and the ECC
  repair source of section 2.3. Transport and scheduling of
  snapshots (where they are copied, how often) are operator
  concerns; the engine guarantees that any snapshot it wrote
  verifies, and says so in `health`.

Claim R1: a store restored from a snapshot is indistinguishable
in behavior from the original at the snapshot's sequence number:
same chain head hash, same live scores, same verification result.
Falsifier: the restore drill runs in CI on every release —
snapshot a randomized store, delete the original, restore, and
diff chain head, all live scores, and a full verification.
Claim R2: a snapshot with one altered byte fails its own
verification before restore begins. Falsifier: mutation tests on
the bundle, as in H1.

## 5. Query language (LQL)

A small, read-only language over the core. Grammar budget: the
whole language is specified in the package docs on one page, and
anything outside the grammar is a parse error with a position —
never a partial execution.

Core constructs:

```
CLAIM <id>                      one claim, full record
CLAIMS WHERE <filter>           set of claims
WHY <claim>                     support ancestry (as `why` today)
IMPACT <claim> [STRUCTURAL|PROPAGATED TO <value>]
                                dependents closure (section 3)
DEPENDS <claim>                 dependency closure (as today)
AS_OF <timestamp> <query>       run any query against the state
                                at that time
EVENTS WHERE <filter>           audit-trail reads over the log
DECISIONS WHERE <filter>        decisions, with basis sets
HEALTH                          the section 2.4 report
```

Filters are comparisons over named fields (`status`, `writer`,
`tier`, `score`, `kind`, combined with `AND`/`OR`). Every LQL
construct compiles to a core call; there is no string-built SQL
anywhere in the path.

Claim Q1: for every construct, the LQL result equals the
corresponding core API result on the same store — property-tested
across randomized stores and queries.
Claim Q2: malformed input fails with a parse error naming the
position, and executes nothing. Falsifier: a fuzz corpus of
mutated valid queries must produce only parse errors or valid
results — never a panic, never a partial write (LQL cannot write
at all; the store's file hashes are asserted unchanged across the
fuzz run).

## 6. Interfaces

- **Python API:** the 0.12.0 surface, unchanged in meaning, plus
  `impact`, `snapshot`, `restore`, `health`, `verify(deep=True)`,
  and `query` (LQL). Engine selection: Rust core by default,
  `engine="python"` (or `EPISTEMIC_LEDGER_ENGINE=python`) selects
  the reference implementation.
- **CLI:** `impact`, `query`, `snapshot`, `restore`, `health`
  join the existing `demo`, `verify`, `kill-metrics`.
- **MCP server:** tools `get_claim`, `list_claims`, `why`,
  `impact`, `depends_on`, `assert_claim`, `challenge`,
  `record_decision`, `verify_store`, `health`, `kill_metrics`,
  and `query` (LQL). Tool inputs are typed schemas, not free
  text, except `query`. Write tools pass through the same
  governed paths as the API — a challenge issued over MCP is the
  same signed event as one issued from Python.
  The MCP sync rule applies: any engine change that alters a
  tool's behavior updates the tool schemas, the server docs, and
  the changelog in the same change.

Claim M1: for a fixed scenario script, the MCP tools, the CLI,
and the Python API return identical results (the script runs all
three faces in CI and diffs them).

## 7. Adversarial battery

Runs in CI on every release, against the Rust engine and, where
the surface is shared, the Python reference:

- **History attacks:** bit flips, deletion, insertion, reorder,
  full rewrite with recomputed hashes (must fail on signatures),
  full rewrite with copied signatures over altered payloads.
- **Crash attacks:** process kill at randomized points during
  append bursts; torn final writes at every byte offset of a
  record; projection deleted outright (must rebuild from the log
  to an identical state); projection corrupted (must be caught
  by verification, then rebuilt).
- **Corruption drills:** per-segment corruption with snapshot
  repair (E3); corruption with no snapshot (recovery stops at
  the first bad record and reports the loss exactly).
- **Concurrency:** a second writer is refused (DESIGN-12);
  read-only openers during writes observe only complete records.
- **Query fuzzing:** LQL fuzz corpus (Q2); impact on adversarial
  graph shapes (deep chains, wide fans, near-cycles).

Every drill ends with `health` and a full verification; the
battery fails if either reports clean over damage (E4).

## 8. Performance budgets

"Fast" is a set of numbers enforced in CI, measured on the CI
runner class and published in the release notes with the hardware
stated. Budgets are set at spec time from the reference workloads
below; a regression past budget fails the build like any other
test.

Reference workloads:

- **Append:** sustained single-writer appends, fsync per record
  (the durability default). Budget: ≥ 2,000 records/second.
- **Verify:** full chain verification. Budget: ≥ 50,000
  records/second (hashing is the floor; signatures verified in
  the same pass).
- **Open:** store open with projection present. Budget: ≤ 250 ms
  at 100,000 events.
- **Impact:** structural closure on the reference graph (10,000
  claims, ~40,000 edges, decision nodes included). Budget:
  ≤ 100 ms; propagated impact ≤ 500 ms.
- **Query:** LQL point and filtered-set queries at 100,000
  events. Budget: ≤ 50 ms.

These budgets are deliberately set to be met with headroom by a
Rust core, and the Python reference implementation is explicitly
exempt (it is the correctness oracle, not the performance
surface). If a budget proves unmeetable on CI hardware, the
budget is amended in this memo with the measurement attached —
never silently relaxed in code.

## 9. Migration and compatibility

- `migrate` (API + CLI) reads a 0.12.0 store, replays its
  events.jsonl into the chained format (sequence assigned in log
  order, genesis prev_hash), rebuilds the projection, and runs a
  full verification. Events keep their original ids, timestamps,
  actors, and payloads; the migration itself is recorded as the
  new log's first checkpoint note, naming the source format.
  Unsigned legacy events are marked as such in the migrated log —
  migration does not retroactively sign history it cannot attest.
- The 0.12.0 test suite passes against the Rust engine through
  the unchanged API, and against the Python engine as today.
- Differential testing: randomized operation scripts run against
  both engines; any divergence in scores, closures, or
  verification verdicts fails the build. The Python engine is the
  oracle because it is the implementation the research results
  were produced with.

Claim G1: for every store in the migration test corpus (including
the prototype's own validation stores), migration completes,
verification passes, and every live score matches the pre-migration
store exactly.
This does not establish tamper evidence for pre-migration history:
a 0.12.0 log could have been altered before migration and no
chain can prove otherwise after the fact. Migration attests the
history as found, and says so.

## 10. Build order (approved 2026-10-27)

1. This spec, landed as a PR, docs build green.
2. Rust core: storage, chain, signatures, checkpoints,
   verification, health, recovery (sections 1–2).
3. Python bindings at parity + migration (D1, section 9).
4. Impact analysis and decision nodes (section 3).
5. Snapshots and restore drill (section 4).
6. LQL + MCP + CLI faces (sections 5–6).
7. Adversarial battery and budgets wired into CI (sections 7–8).
8. Release as 0.13.0 through the existing protected release flow.

## Claims register

| Claim | Substance | Falsifier lives in |
|---|---|---|
| H1 | Any history mutation is detected, first bad seq named | §1.1 battery |
| H2 | Forged/re-attributed events fail signature checks | §1.1 rewrite-with-wrong-keys |
| H3 | Checkpoint segments verify independently | §1.2 segment tests |
| H4 | Verification is complete, not sampled | §1.2 (scope note stated) |
| E1 | Crashes never yield a silently wrong store | §7 crash attacks |
| E2 | Read-only openers cannot mutate the store | §2.2 file-hash tests |
| E3 | Snapshot-backed corruption is repaired exactly | §7 corruption drills |
| E4 | Health never reports clean over damage | §7 battery epilogue |
| I1 | Impact closure equals brute-force closure | §3.2 property tests |
| I2 | Dry-run impact equals the real revision | §3.2 property tests |
| I3 | Impact meets its budget and reports caps | §8 reference graph |
| R1 | Restore reproduces the original at the snapshot seq | §4 CI drill |
| R2 | A mutated snapshot fails before restore | §4 mutation tests |
| Q1 | LQL results equal API results | §5 property tests |
| Q2 | Malformed LQL executes nothing | §5 fuzz corpus |
| M1 | API, CLI, and MCP return identical results | §6 scenario diff |
| G1 | Migration preserves every live score | §9 migration corpus |
