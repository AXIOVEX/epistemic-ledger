# DESIGN-15 — The Ledger as Arcturus's Substrate: Anchoring, Tenancy, and Governed Record Types

Status: design memo, approved by the owner 2026-10-29. Spec first, per this
project's flow: this memo changes no behavior. Each stage below lands as its
own pull requests with its claims' tests written to be able to fail.

## 1. Why this memo exists

AXIOVEX Arcturus — Axiovex Systems' workforce and capability-matching
program — names this ledger as its store of record. The program's
architecture supplement carries the design in whole: the database is the
DN-005 epistemic ledger (absolute append-only, revisions as new records,
nothing deleted), held to the Ledger Standard v1 (Addendum C): ACID
transactions, WORM-pattern retention, RFC 9162-style transparency-log
verifiability, W3C PROV provenance, and an adversarial robustness battery
at every release. A stand-in store (D1/SQLite) serves only "until the
ledger package itself is production-hardened."

Two program rules bind everything below:

- **The coupling rule.** The product never outruns the ledger's *proven*
  guarantees. A product feature that needs a guarantee the ledger has not
  yet proven in test is gated until the proof exists. Section 8 turns that
  rule into a gate table.
- **Description discipline.** The ledger is described only by the legs it
  has currently proven, never by absolutes. Section 2 is written in that
  discipline.

## 2. Where the ledger stands (release 0.13.1)

Proven, each by tests that are shown able to fail:

- **Append-only chained store.** Every record is hash-chained and
  Ed25519-signed; the storage layer exposes no update or delete path for
  records; torn tails are truncated only at the uncommitted tail and the
  repair is verified (DESIGN-13, DESIGN-14).
- **Verified writes.** Every write the ledger calls committed is read
  back and verified first, in both the Python engine and the Rust core;
  a partial or empty record never stands as committed (DESIGN-14).
- **ACID projection, log is truth.** The SQLite projection is
  transactional and exactly rebuildable from the chain; the rebuild is
  proven byte-identical by a differential test.
- **Merkle checkpoints.** RFC 9162-style checkpoint trees over
  1,024-record segments, verified inside the store; batch signature
  verification with sequential fallback as the arbiter.
- **Decisions and impact.** Decisions are records with an immutable
  basis; impact analysis answers, structurally and by propagated
  re-scoring, what a challenged claim or a changed decision affects.
- **Adversarial battery at every release.** Twelve tamper drills gate CI
  as a required check, alongside the DESIGN-13 performance budgets, all
  currently met.

Not yet established:

- **The transparency leg's outer half.** Checkpoints are verified
  in-store only. Nothing yet anchors a checkpoint root outside the
  operator's own systems, no third party can check an inclusion or
  consistency proof, and no tenant can pin a tree head.
- **The provenance leg's export.** Provenance is recorded natively
  (actor, action, basis, derivation links) but there is no W3C PROV
  export.
- **Tenancy machinery.** The store is one chain for one writer
  community. There are no per-tenant partitions with their own keys, no
  key enrollment or revocation records, no payload-commitment records,
  and no erasure machinery.
- **Distribution of the Rust core.** The chained store ships in the
  repository but not in the PyPI package, which is pure Python; the
  sdist does not carry the Rust sources.

## 3. Decisions

**D1 — Deployment shape: a ledger service with one chained store per
tenant partition.** A tenant partition is physical, not logical: its own
directory (chained log, projection, snapshots), its own signing keys,
its own checkpoints. This is deliberately distinct from DESIGN-11's
partitions, which are predicate-policy partitions *inside* one store for
scoring; a tenant partition never shares a chain with another tenant.
SQL stores (D1 or any other) may hold projections only; every projection
must be rebuildable from its partition's chain, and the chain alone must
pass verification. The package's scope is the store, the proofs, and the
record machinery; the service wrapper that routes requests to partitions
is the product's, built on the package's interfaces (library, CLI, LQL,
MCP).

**D2 — Anchoring: signed tree heads, proofs, and witnesses.** Each
checkpoint produces a *signed tree head* (STH): the record count it
covers, the Merkle root, the checkpoint sequence, a timestamp, and the
checkpoint key's identity, signed by the partition's checkpoint key.
On top of STHs:

- *Inclusion proofs* — an RFC 9162-style audit path from any record's
  leaf to its checkpoint root, verifiable without access to the store.
- *Consistency proofs* — between any two checkpoints of one partition,
  proving the later history extends the earlier one.
- *External anchoring* — the STH (never record data) is submitted to one
  or more *witnesses*: append-only stores not administered by the ledger
  operator. A witness is configuration (an endpoint and a protocol),
  never code in the package. The witness's receipt is recorded in the
  partition itself as an `anchor` record in the next segment, so the
  chain carries its own anchoring history.
- *Tenant pinning* — a tenant keeps the STHs it has seen. Two validly
  signed STHs at the same tree size with different roots are proof the
  operator equivocated; verification surfaces that as a hard error,
  never a silent choice between forks.

**D3 — Key custody: enrollment is a ledger act.** Writers already sign
every record. What is missing is the directory: `key_enrollment` and
`key_revocation` become governed record types written into the
partition's genesis segment, so a partition is self-describing — its own
chain states who was allowed to write, from when, and until when.
Verification takes enrollment into account: a record signed outside its
key's enrollment window fails verification. Checkpoint keys enroll the
same way. Private keys never enter the package or the store; custody is
the operator's and each tenant's (KMS or equivalent).

**D4 — Identified payloads never enter the ledger body: commitments and
erasure.** A `commitment` record carries a keyed hash (HMAC-SHA-256,
per-tenant key, per-record random salt held with the payload) of an
identified payload that lives elsewhere, encrypted under its own key.
The ledger proves a payload existed and has not changed; it never holds
the payload. Erasure works by destroying the payload's key and salt:
the payload becomes unrecoverable while the commitment, and the chain
around it, remain verifiable. The act is recorded as an `erasure` record
referencing the commitment, signed by the tenant's data-controller key.

**D5 — Governed record types: a schema registry, and the Arcturus pack.**
The package gains a record-schema registry. A schema is a versioned
document registered by name (for example `arcturus.source_terms` version
1); appends of a registered type are validated at append time and
refused on violation; unregistered types keep today's exact behavior.
Schemas are themselves recorded in the store as `schema` records before
first use — a partition describes its own record types, and a schema
change is a new version record, never an edit. The Arcturus pack ships
in this repository as data plus a thin module defining the program's
record types: `source_terms` (a data source's terms, recorded before
its first data is accepted), `consent`, `disclosure` (written before
any cross-tenant release), `match_introduction` (which by schema ends
at contact exchange — the type has no fields for anything after),
`key_enrollment`, `key_revocation`, `anchor`, `erasure`, and
`poam_entry`. Appending a `disclosure` record returns a *receipt* bound
to that record's hash: unforgeable, and valid for exactly that one
disclosure. Suppression and matching thresholds live in the store as
versioned policy records (the existing policy machinery), never as
constants in code.

**D6 — Provenance export: W3C PROV.** An export function renders a
partition (or a filtered slice) as W3C PROV (PROV-JSON, with a JSON-LD
context): records are entities, appends and decisions are activities,
actor keys are agents, and the dependency graph's support/derivation
links become derivation relations. The export header carries the head
hash and the latest STH, so an export can be checked against the
anchored chain by anyone holding the STH.

**D7 — Distribution: platform wheels.** The release workflow gains
maturin wheel builds (Linux, macOS, Windows; CPython 3.10–3.13)
alongside the pure-Python wheel, which remains the fallback. The sdist
gains a manifest carrying the Rust sources and the committed lockfile.
The PyPI readme is refreshed to the current feature set in the same
release. For Arcturus this is deployment-required, not cosmetic: a
deployed service cannot depend on a chained store that its package
index does not ship.

## 4. Stage 1 — Anchoring and proofs

- **A1.** After a checkpoint is anchored, any rewrite of pre-anchor
  history is detected by consistency verification against the anchored
  STH. *Falsifier:* the battery gains a drill that anchors, rewrites
  history below the anchor, and requires detection.
- **A2.** For any record covered by an anchored checkpoint, an inclusion
  proof verifies against the anchored root with no access to the store.
  *Falsifier:* a standalone verifier, given only the record, its proof,
  and the STH, accepts valid proofs and rejects a proof for a mutated
  record, a wrong record, and a wrong checkpoint.
- **A3.** A verifier holding a pinned STH detects equivocation: two
  validly signed STHs at the same tree size with different roots
  produce a hard fork error. *Falsifier:* a drill that signs two such
  STHs with the real checkpoint key and requires refusal.
- Anchoring is asynchronous to appends: the DESIGN-13 append budget
  holds with anchoring enabled (the battery's bench is the falsifier).
  Proof generation and proof verification each complete within 50 ms on
  the reference store class (100k records).

**Stage 1 implementation notes (2026-10-30).** The STH is a JSON
object `{tree_size, root, checkpoint_seq, timestamp, key_id,
signature}`. `tree_size` is the checkpoint's last covered sequence
number; `root` is the checkpoint's Merkle root exactly as DESIGN-13
computes it — the segment format does not change, and existing
snapshots and health reports stay valid. The signature is Ed25519
over SHA-256 of the domain separator `ELSTH1` followed by the
RFC 8785 canonical JSON of the unsigned head — the sign-the-hash
shape the chain uses for records. STHs are issued per checkpoint at
the canonical 1024-record segment, whatever segment a health report
used. The checkpoint key's seed is passed per issuance and never
stored, the same custody as writer seeds. Consistency between two
heads is proven by *chain linkage*: the intervening checkpoints in
order, each carrying its predecessor's root in `prev_root`, checked
for contiguity of sequence ranges and exact endpoint equality.
DESIGN-13 does not bind `prev_root` into the segment root, so a
single-tree RFC 9162 consistency proof does not apply to this
structure; the linkage proof is the consistency proof for a
checkpoint chain, its cost is one hash comparison per checkpoint,
and any rewrite below an anchored head changes some checkpoint's
root and breaks a link or an endpoint. External witnessing stays
configuration, not package code (D2): the package issues and
verifies heads and proofs; submitting a head to a witness and
recording the receipt as an `anchor` record belongs to the record
pack in Stage 3.

## 5. Stage 2 — Tenancy, keys, commitments, erasure

- **T1.** No package API path reads from or appends to a partition other
  than the one opened, and verification enforces enrollment windows.
  *Falsifiers:* a cross-partition probe suite (reads, appends, and
  proof requests against a second partition all refused), and records
  signed before enrollment, after revocation, or by unenrolled keys
  failing verification.
- **T2.** Without the tenant's HMAC key, the store's bytes do not yield
  payload content: a dictionary attack over a known payload space fails
  against the commitments in the store, while the key holder's
  recomputation verifies. *Falsifier:* the drill runs both directions.
- **T3.** After an `erasure` record and destruction of the payload key
  and salt, the payload is unrecoverable from any ledger artifact,
  while chain verification, checkpoints, and proofs over the affected
  region still pass. *Falsifier:* an erasure drill that attempts
  recovery from the store, its snapshots, and its exports.

**Stage 2 implementation notes (2026-10-30).** Tenancy lands as a
guarded convention over the store's existing physical shape: a
tenant id is a slug (1-64 chars of [a-z0-9-], starting
alphanumeric), a partition directory is root + slug with a
containment check behind it, and the probe suite aims every API
path at a second partition (reads, appends, escape spellings, a
second live writer) — all refused or answered from the opened
partition alone. Key governance folds the chain in sequence
order: a `key_enrollment` record (payload key_id, pubkey, role)
opens a window at its own sequence, a `key_revocation` closes it
at its sequence, and governed verification checks every record's
signature against the window in force at that record's sequence.
Governance records are effective only when signed by the genesis
key — whose public key the verifier holds out of band, the same
trust shape as the existing pubkeys map — or by a key holding
the admin role in an open window; the genesis key cannot be
revoked in-band. Roles are writer, checkpoint, and admin; an
ordinary record signed by a key holding any other role is a
violation. Governed verification is additive (`verify_governed`
beside `verify`, whose semantics do not change) and sequential
rather than batch, so it is the audit path, not the hot path;
no DESIGN-13 budget applies to it. Checkpoint-key windows are
read from the governance report (`key_effective_at` at the
head's tree size) by the verifier side. Commitments and erasure
(T2-T3) are the stage's second half and land separately.

**Stage 2b notes (2026-10-30).** Commitments are a Python-side
construction over ordinary appends: `commitment_for` computes
HMAC-SHA-256 under the tenant's key over salt || payload, the
`commitment` record carries only the hex value and a caller
reference, and the `erasure` record names the commitment it
retires. Nothing in the chain format changes. The drills are
the claims: the dictionary attack runs over a known payload
space with every keyless construction an artifact holder can
compute, and the erasure drill scans the live store, a snapshot
taken before the erasure, and the record export for the
payload, the salt, and the key. What this does not establish:
that an operator actually destroyed a key — destruction happens
outside the ledger, and the erasure record attests that the act
was recorded, not that it occurred.

## 6. Stage 3 — Schema registry and the Arcturus pack

- **R1.** Appends that violate a registered schema version are refused
  at append time with the violated field named; appends of unregistered
  types behave exactly as they do today. *Falsifier:* a refusal suite
  over the pack's types plus a regression run of the existing suite.
- **R2.** A disclosure receipt validates for exactly the disclosure
  record it was issued from — not for another disclosure, another
  partition, or a mutated record. *Falsifier:* receipt-swap and
  receipt-mutation drills.

## 7. Stage 4 — PROV export; Stage 5 — Wheels

- **V1.** The PROV export accounts for the store exactly: every exported
  activity maps to exactly one ledger record, the export's stated head
  hash equals the store's, and a re-derived export of an unchanged store
  is identical. *Falsifier:* a round-trip accounting test over generated
  stores, run in the battery.
- **W1.** A clean environment with no Rust toolchain installs the wheel
  from the package index and runs the chained-store path end to end
  (open, migrate, snapshot, verify). *Falsifier:* a CI job that installs
  the built wheel with the toolchain scrubbed from its environment and
  runs that smoke path.
- **G1 (all stages).** The DESIGN-13 budgets and the full battery —
  extended per stage with that stage's drills — stay green at every
  release. A stage that cannot keep G1 does not ship.

## 8. Coupling gates for Arcturus

- Single-tenant use of the ledger as it stands (0.13.1): **ungated** —
  the proven legs of section 2 cover it.
- Cross-tenant disclosure in production: gated on **Stage 2 + Stage 3**
  (`disclosure` type, receipts, partition isolation probes passing).
- Any external statement that a history is independently verifiable:
  gated on **Stage 1**.
- Erasure representations to partners or participants: gated on
  **Stage 2** (T3 proven).
- Partner-facing provenance exports: gated on **Stage 4**.
- Deployed service on the package from the index: gated on **Stage 5**.

## 9. Honest scope — what this does not establish

- Anchoring proves a history existed by the anchor time and has not
  been rewritten since. It does not prove the history was true when it
  was written; nothing in this program can prove that.
- A commitment hides a payload only as well as the tenant's key and
  salt custody. If both leak, a low-entropy payload is dictionary-
  attackable; the pack's schema guidance (which payload classes may be
  committed, and how they are salted) is part of the Stage 3
  deliverable, not an afterthought.
- The package issues disclosure receipts; it cannot force an
  application to demand one before releasing data. That rule lives in
  the product's data-access layer and its access-matrix probe suite.
  This memo's contract ends at receipts that cannot be forged or
  reused.
- Fork detection requires someone to pin and compare. A tenant who
  never checks an STH cannot detect equivocation directed only at them;
  anchoring to independent witnesses narrows that gap to checkpoints no
  witness has seen, and closes it for witnessed ones.
- No CUI or FIPS claims. The chain's cryptography (Ed25519, SHA-256) is
  not FIPS-validated; controlled-information classes remain gated in
  the product program, outside this package.
