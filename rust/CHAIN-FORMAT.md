# Chain format v1 (implements DESIGN-13 section 1)

The byte-level format both engines (Rust core, Python reference)
must produce identically. The shared test vectors are the authority:
any disagreement between an implementation and the vectors is a bug
in the implementation, never in the vectors.

## Canonical payload JSON

The payload is canonicalized as JSON per RFC 8785 (JSON
Canonicalization Scheme): object keys sorted, no whitespace,
minimal string escaping, and numbers serialized with the
ECMAScript number-to-string algorithm (so `1.0` is `1`,
`0.000001` is `0.000001`, `1e-7` is `1e-7`, `1e30` is `1e+30`).
The canonical form is a UTF-8 string.

## Hash input

```
"ELCHAIN1" ||
for each field in [seq, t, actor, type, payload, prev_hash]:
    u32be(byte length of field) || field bytes
```

- `seq`: decimal ASCII, no leading zeros.
- `t`, `actor`, `type`: the raw UTF-8 strings.
- `payload`: the canonical payload JSON string.
- `prev_hash`: 64 lowercase hex characters; the genesis record
  uses 64 zero characters.

`hash = SHA-256(hash input)`, written as 64 lowercase hex chars.

## Signature

`sig = Ed25519-sign(writer_seed, hash_bytes)` over the 32 raw hash
bytes, written as 128 lowercase hex chars. Absent only for the
reserved `system` actor in migrated legacy events.

## Log line

One record per line in `events.log`:

```
<crc> <json>\n
```

- `<json>`: compact JSON object with fields in this order: `seq`,
  `t`, `actor`, `type`, `payload`, `prev_hash`, `hash`, `sig`
  (`sig` omitted when absent). The payload appears as a JSON value;
  verifiers re-canonicalize it for the hash check.
- `<crc>`: CRC32C (Castagnoli) of the `<json>` bytes, 8 lowercase
  hex chars. A trailing line that is incomplete, lacks the final
  newline, or fails its CRC is a torn tail, never a valid record.
