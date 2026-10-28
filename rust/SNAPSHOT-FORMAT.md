# Snapshot bundle format v1

A snapshot (DESIGN-13 section 4) is a directory — the *bundle* —
holding exactly two files:

| File | Contents |
| --- | --- |
| `events.log` | The store's chained log (see CHAIN-FORMAT.md), byte for byte. |
| `manifest.json` | The manifest below, as pretty-printed JSON. |

## Manifest

```json
{
  "format": 1,
  "kind": "epistemic-ledger-snapshot",
  "events": 7,
  "head_hash": "<hex sha256 of the last record, or the genesis prev-hash>",
  "segment": 1024,
  "checkpoints": [ { "first_seq": 1, "last_seq": 1024, "root": "<hex>", "prev_root": "<hex>" } ],
  "log_sha256": "<hex sha256 of the events.log bytes>",
  "bundle_hash": "<hex, defined below>"
}
```

`checkpoints` is the checkpoint set over the log: one checkpoint
per complete segment of `segment` records, Merkle roots per
CHAIN-FORMAT.md / RFC 9162, chained by `prev_root` exactly as the
health report computes them. A trailing partial segment has no
checkpoint.

`bundle_hash` is the SHA-256 of:

```
log_sha256 (as ASCII hex) || "\n" || canonical_json(manifest with "bundle_hash" set to "")
```

where `canonical_json` is the RFC 8785 canonicalization used by
the chain format.

## Verification

Verifying a bundle, from the bundle alone:

1. The manifest parses, `format` is 1, `kind` matches.
2. SHA-256 of `events.log` equals `log_sha256`.
3. The recomputed `bundle_hash` equals the recorded one.
4. Every log line parses (CRC32C per CHAIN-FORMAT.md) and the
   full chain verifies: sequence numbers 1..N, prev-hash linkage,
   and every record hash recomputed from its fields. Signatures
   are *not* checked here — a bundle carries no keys; signature
   verification remains `Store::verify` with the writers' keys.
5. The record count and chain head equal `events` and
   `head_hash`.
6. The checkpoint set recomputed from the log equals
   `checkpoints`.

Any failure stops verification with the specific mismatch; a
restore runs this verification to completion before writing a
single byte.

## Scope, honestly

These checks detect any alteration of the bundle as written —
one flipped byte anywhere fails step 2, 3, 4, or 6. A bundle
rewritten wholesale and consistently (log, checkpoints, and
hashes all recomputed by the rewriter) is indistinguishable from
a genuine one by the bundle alone; that is what record
signatures and external anchoring of checkpoint roots are for
(DESIGN-13 section 1). Snapshots are the unit of backup and the
repair source for corrupted segments (section 2.3); where they
are stored and how often they are taken are operator concerns.
