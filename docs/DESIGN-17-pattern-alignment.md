# DESIGN-17 — Winning-combination alignment: the ledger layer as a product

Status: design memo (2026-11-01). Claims P1–P6, G1 below are
the contract; implementation proceeds stage by stage against
them, as with DESIGN-13/15/16.

## 1. Why

On 2026-11-01 the framework's canonical pattern note (the
winning combination, issued from the projected-constraints
program) named this package "the ledger layer as a product":
every framework project keeps an epistemic ledger in the
pattern's shape — every material claim with statement,
source, date, status, confidence, falsifier, and a
does-not-establish line; corrections as append-only
reclassifications; a matrix generated from the ledger by
script; a layered map as the primary surface; an engine
that computes mechanically from the ledger's claims; and a
verification gate that recomputes every downstream layer
and fails on divergence.

This package is the ledger half of the future shared
component (the RCPH side is currently the engine half).
For other projects' ledgers to be produced and checked by
this package, its data model and its generated exports must
speak the pattern natively. That alignment is this memo.

## 2. Where the shipped model stands against the pattern

Measured against 0.14.0's claim record (claim_id, txn_from,
statement, valid window, score, score_kind, status,
materiality, critical, entrenchment, writer; chain events
carry t and actor):

- statement — present.
- date — present (txn_from; event timestamps).
- status — present, with append-only lifecycle transitions
  (supersede / set_claim_status, reason bundle required).
- confidence — present (prior at assertion; the computed
  score is the engine's settlement of it).
- source — NOT a first-class claim field (writer/actor is
  who wrote the record, not where the claim comes from).
- falsifier — NOT a field (falsifiers live in this
  program's design memos, not in the package's data model).
- does-not-establish — NOT a field.
- append-only reclassification — present by construction
  (the chain is append-only; no mutator edits a claim's
  fields in place).
- generated matrix / layered map — NOT present (the PROV
  export is a generated export, but it is a provenance
  rendering, not the pattern's matrix or map).
- verification gate over generated layers — NOT present
  (chain verification exists; nothing recomputes a matrix
  or map and diffs it).
- engine — present in substance: scoring settlement,
  structural and propagated impact, and chain verification
  compute mechanically from the records. What the pattern
  adds is pre-registered expectations the engine must
  reproduce exactly (a pinned golden ledger).

## 3. Decisions

- **D1 — Fields are additive and optional.** `source`,
  `falsifier`, and `does_not_establish` become first-class
  claim fields on assertion, carried in the claim row, the
  chain event, and projection rebuild. Existing stores open
  unchanged; claims asserted before this change read back
  with null pattern fields. (Ships as 0.15.0, a minor.)
- **D2 — One pattern module.** `epistemic_ledger.pattern`
  holds the matrix generator, the map generator, and the
  gate — pure functions of the ledger's records, no wall
  clock, no project-specific content of any kind (the
  future shared component extracts from here).
- **D3 — Matrix shape.** Rows are claims (live and
  terminal), columns are the pattern fields plus the
  settled score; ordering is by assertion sequence;
  rendering is JSON and Markdown from one canonical dict,
  so the gate compares one thing, not two renderings.
- **D4 — Map shape.** Three layers: the ledger headline
  (record counts by status, head hash, latest tree head
  where present) → claim groups (by status, then by
  decision linkage) → evidence (support edges and source
  events). Every element carries the ledger ids it came
  from; nothing appears that is not in the ledger.
- **D5 — The gate is a recompute-and-diff.** Given a
  ledger and a matrix/map pair, the gate regenerates both
  from the ledger and fails on any byte of divergence,
  through the library and the CLI. A hand-edit downstream
  is a failing gate, never a silent difference.
- **D6 — Engine expectations are pre-registered.** A
  golden ledger (fixed seeds, fixed timestamps) ships in
  the test suite with its settled scores, impact results,
  and verification outcome pinned; the engine must
  reproduce them exactly, in CI, on every change.

## 4. Stages

1. This memo.
2. Claim fields (P1, P2): fields end to end — assertion,
   storage, event, rebuild, reads.
3. Matrix generator (P3).
4. Map generator (P4).
5. Gate + golden engine expectations (P5, P6).
6. Conformance demonstration: this program's own design
   claims (DESIGN-13/15/16/17) entered through the package
   as a ledger, its matrix and map generated into the
   repo's docs, the gate wired into CI; then release
   0.15.0 through the standard release-tier gate.

## 5. Claims

- **P1 (fields round-trip).** A claim asserted with
  source, falsifier, and does_not_establish carries all
  three in its live row, in its chain event, and after a
  full projection rebuild, unchanged. *Falsifier:* the
  field-diff drill across assert → rebuild → read.
- **P2 (append-only).** Pattern fields obey the existing
  lifecycle: they change only through supersede or a
  status transition carrying its reason bundle; the
  original assertion event is never altered. *Falsifier:*
  a drill that supersedes a field-bearing claim and checks
  the original event byte-for-byte.
- **P3 (matrix is generated, completely).** The matrix is
  a pure function of the ledger's records: regeneration
  from the same ledger is byte-identical; every live and
  terminal claim appears exactly once; every row traces
  to a claim id in the ledger. *Falsifier:* determinism
  and completeness drills.
- **P4 (map is generated, traceable).** The map renders
  exactly the generated data: its headline equals the
  ledger's verified headline state, and every element
  carries the ids of the records it renders. *Falsifier:*
  headline and traceability drills against a live ledger.
- **P5 (gate).** The gate passes on artifacts regenerated
  from the ledger it checks, and fails on a one-byte
  change to either artifact, on a missing claim row, and
  on a headline that disagrees with the ledger.
  *Falsifier:* the tamper drills themselves.
- **P6 (engine expectations).** On the pinned golden
  ledger, the engine's settled scores, impact results,
  and verification outcome equal the pre-registered values
  exactly. *Falsifier:* the golden test.
- **G1 (no hardcoding, no breakage).** The pattern module
  contains no project-specific identifiers, field names
  beyond the pattern's, or content; pre-0.15 stores open
  and verify unchanged. *Falsifier:* the existing battery
  running unmodified against old-format stores, plus a
  source scan of the module.

## 5.5 Stage notes

**Stage 2 (claim fields) — implemented.** `source`,
`falsifier`, and `does_not_establish` are first-class
optional claim fields: three nullable columns on the
claims table (added to the CREATE TABLE and backfilled by
`_ensure_columns`, the writer-column precedent), three
kwargs on `assert_claim`, carried on the assert event's
payload, read by the rebuild fold (pre-0.15 logs, whose
payloads lack the keys, fold with null fields), and copied
forward by both version-copy paths so score revisions
never drop them. One naming collision, resolved in the
open: `supersede` already takes a required bundle
`source` — the source of the correction judgment, carried
on the supersede event. The successor claim's field is
set by a new `claim_source` kwarg, defaulting to the
bundle source; `falsifier` and `does_not_establish` are
never inherited — a corrected claim restates its own.
Drills in `tests/test_pattern_fields.py`: field
round-trip through reads, a score revision, and a full
projection rebuild; fieldless claims read null; a
hand-written pre-0.15 log folds clean; supersede leaves
the original assert event byte-identical (P1, P2).


**Stage 3 (matrix generator) — implemented.**
`epistemic_ledger.pattern.build_matrix` folds the
ledger's event list into one canonical dict: a row per
claim in assertion order (claim_id, statement, source,
date, status, settled confidence, falsifier,
does-not-establish, and the superseded-by linkage that
makes reclassification visible), plus per-status counts.
The source of truth is the event list, not the live-claims
API — terminal claims appear exactly once, as P3 requires.
JSON and Markdown renderings derive from the one dict;
the JSON form is the byte form the stage-5 gate will
compare. Drills in `tests/test_pattern_matrix.py`:
completeness and traceability over a ledger with a live, a
revised, a superseded, and a dead claim; agreement with
the live projection on every shared field; byte-identical
regeneration.


**Stage 4 (layered map) — implemented.** `build_map`
renders the three layers from the same fold: the headline
(event, claim, and decision totals plus the matrix's
per-status counts — pinned by drill against
`verify_store()`'s verified event count), claim groups by
status (a checked partition of the claim set), decisions
with their basis claim ids and event ids, and per-claim
evidence — the ids of every event whose payload references
the claim, so a support edge appears in both endpoints'
evidence. For the Python claim ledger there is no head
hash (hashes live in the chained store); the headline is
counts and totals, and no head field is faked. JSON and
Markdown renderings derive from the one dict.


**Stage 5 (gate + golden expectations) — implemented.**
`check_pattern` regenerates both canonical JSON forms
from the ledger's records and byte-compares them against
the artifacts under check, naming the diverging layer;
the CLI grows `pattern-export` (writes matrix.json,
matrix.md, map.json, map.md) and `pattern-check`
(regenerates all four and diffs each file — a hand-edit
to a Markdown surface is drift too; a missing file is a
failing gate). The golden test pins expectations derived
from the documented rules rather than captured from the
implementation: the Jeffrey settlement of an evidentially
supported claim (supporter at 1.0 → 0.9 exactly, at 0.0
→ 0.2 exactly, from p_given 0.9 / p_given_not 0.2), the
supporter's structural impact (exactly the supported
claim at distance 1), verification counts, and the
matrix's confidence tracking the engine's settled score
at each step (P5, P6).


**Harmonization adoption (2026-11-01): canonicalize
before you hash.** The Spec-Kit AEE chat's pattern note
was assessed against this package and adopted in full;
no ratified local decision conflicts. Already conformant:
the chain hashes RFC 8785 canonical JSON, never raw file
bytes, and the pattern layers carry no raw-byte
provenance hash. Two real gaps the note caught in the
stage-5 work, both fixed here: the CLI's pattern commands
wrote and read artifacts in text mode (a Windows export
would have been CRLF, and a text-mode read would have
hidden CRLF drift — the note's exact failure), and
`pattern-check` opened the store through the shared CLI
path, taking the writer lock and risking repair — a gate
must write nothing. Now: both commands run before the
Ledger open and read the log through `events_from_log`
(a pure read), artifacts are written and compared as
bytes with pinned LF, and a `.gitattributes` pins eol=lf
across the repo's text formats (verified CRLF-free
beforehand, so the pin is noise-free). Drills: exported
bytes contain no CR; a check run leaves the store tree
byte-identical and works on a bare log with no database;
a CRLF-converted artifact fails the gate.

## 6. Honest scope

The package can produce and check a ledger in the
pattern's shape; that makes downstream layers provably
faithful to the ledger, never the ledger faithful to the
world. A falsifier field records what would settle a
claim; it does not settle it. The gate proves the matrix
and map are the ledger, rendered — drift is a downstream
defect by definition, and truth still enters only through
the ledger's own discipline.
