# Fuzz targets (DESIGN-16 stage 2)

cargo-fuzz targets over the core's parser and verifier entry
points. The entry functions live in the core crate
(`epistemic_ledger_core::fuzzing`) so the committed corpora can be
replayed as ordinary tests: `cargo test -p epistemic-ledger-core
--test fuzz_corpus` runs every corpus file through the same code
the fuzzers drive, in every PR build, with no fuzz toolchain
installed.

Targets:

- `chain_line` — the chain record parser.
- `canon_json` — JSON parsing + RFC 8785 canonicalization
  (asserts canonicalization is idempotent).
- `sth_decode` — signed-tree-head decoding + signature check.
- `consistency_decode` — consistency-proof bundle decoding +
  verification.
- `manifest_decode` — snapshot manifest decoding.

Campaigns run at the release tier (DESIGN-16 S4): install
cargo-fuzz from the prebuilt release binary, then e.g.
`cargo fuzz run chain_line -- -max_total_time=1800`. Any input
that crashes a target is minimized, committed to
`corpus/<target>/`, and becomes a permanent regression drill via
the corpus test — the campaign counts as green again only with
the drill in place (claim S6).
