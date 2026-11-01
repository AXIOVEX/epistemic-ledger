# The program ledger (DESIGN-17 conformance demonstration)

This directory carries the pattern applied to this
project itself, end to end:

- `program-ledger/events.jsonl` — the ledger. This
  program's design claims (DESIGN-13, DESIGN-15,
  DESIGN-16, DESIGN-17), entered through the package's
  own API with statement, source, falsifier, and
  does-not-establish populated. The log is the sole
  entry point; corrections are supersede events (the
  DESIGN-16 soak claim S3 carries its two revisions
  here, in the open). Only the log is committed — the
  database beside it is a rebuildable projection.
- `matrix.json` / `matrix.md` — the claims × fields
  matrix, generated from the ledger by
  `epistemic_ledger.pattern.build_matrix`. Never edited
  by hand.
- `map.json` / `map.md` — the layered map (headline,
  claim groups, decisions, per-claim evidence ids),
  generated the same way.
- The **gate**: CI's pattern-gate job runs
  `pattern-check` on every push and pull request. It
  regenerates all four artifacts from the committed log
  and fails on any byte of divergence. The check is
  write-free (it reads the log directly and never opens
  the store) and byte-exact (artifacts are compared as
  bytes, with LF newlines pinned by `.gitattributes`).
- `SCHEMA.md` — the pinned claim schema
  (`epistemic-ledger-claims/1`, Amendment 3): field
  provenance rules, the refusal discipline, the
  proposition-fingerprint census, and the coverage the
  gate publishes on every run (the same CI job runs
  `pattern-validate` on this ledger).

Conventions, stated once: statements are compressed
from the design memos, which remain the text of record;
each claim's source names its memo section and the PR
or run carrying its evidence. Priors are 0.5 throughout,
deliberately uninformative — this program settles claims
by running their falsifiers, and the settlement lives in
the sources and the claim lifecycle, not in an invented
number. Two claims (DESIGN-15 R1 and R2) are recorded
as asserted and unsettled: their stage has not been
built, and the ledger says so in their sources.

Regenerate the artifacts after entering new claims:

```
python -m epistemic_ledger pattern-export \
    docs/pattern/program-ledger docs/pattern
python -m epistemic_ledger pattern-check \
    docs/pattern/program-ledger docs/pattern
```

The ledger itself was built by
`tools/pattern/build_program_ledger.py`, kept as the
recipe; re-running it mints fresh claim ids, so the
committed log — not the script — is the ledger of
record.
