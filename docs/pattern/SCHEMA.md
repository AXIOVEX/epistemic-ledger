# The claim schema — `epistemic-ledger-claims/1`

The pinned schema declaration for this ledger's claim
records, per Amendment 3 to the canonical pattern
(ratified 2026-11-01): the schema is declared,
versioned, and pinned beside the artifact; a validator
enforces it in the intake path and in CI; coverage of
the pattern-required fields is published on every
validation run.

## Fields of an assertion (the `assert` event)

| field | type | provenance rule |
|---|---|---|
| `claim_id` | string | System-minted at assertion; never reused, never rewritten. |
| `statement` | string, non-empty | Stated by the claim's author at assertion time. Immutable thereafter: a correction is a new claim that supersedes this one. |
| `prior` | number in [0, 1] | The author's stated credence at assertion time. |
| `source` | string or null | Where the claim comes from, as stated by its author at assertion time (distinct from `writer`, who recorded it). Set at assertion; carried through revisions and supersession only by being restated. |
| `falsifier` | string or null | What observation would settle the claim against itself, as stated by its author at assertion time. Never inherited by a successor claim; restated or null. |
| `does_not_establish` | string or null | The author's stated bound on what the claim, even if true, does not show. Never inherited; restated or null. |

Lifecycle fields (status, settled confidence) are
system-derived — by lifecycle transitions and the
scoring engine, never set by hand — and live on the
claim row and in the generated matrix, not in the
assertion itself.

## Provenance and refusal

The three pattern fields are nullable by design
(DESIGN-17 D1): claims asserted before they existed
fold with nulls, and the absence is *counted*, never
filled in after the fact. What the validator refuses,
loudly and writing nothing, is a violation of the
declared types: a non-string pattern field (refused at
intake, in `Ledger.assert_claim`, before any write),
a missing or non-string statement, a prior outside
[0, 1], or a field of the wrong type found in the log
(refused by `pattern-validate`, naming the event and
the field).

## The proposition fingerprint

SHA-256 over the statement's canonical form (line
endings normalized, whitespace runs collapsed, ends
stripped). The validator recomputes every fingerprint
on every run and publishes the census — total claims,
distinct propositions, duplicates. This package stores
no fingerprint, so there is no stored value to trust;
the census is the check.

**Ledger type (owner's layer-scoped ruling, canonical
pattern note, 2026-11-01): this ledger is an ASSERTION
ledger.** The ruling scopes duplicate propositions by
layer: in a claim ledger (one entry per proposition) a
duplicate fingerprint at intake is refused, per
Glossa-Lab's D-B; in an assertion or evidence ledger
(each assertion a distinct evidence node, where
independent assertions of one proposition are how
corroboration is represented) duplicates are not
refused and not silently kept — they are counted in
the published census, grouped by their recomputed
fingerprint, so corroboration is an explicit, countable
structure. This package's ledger is the second kind,
and its census carries the grouping
(`duplicate_groups`: fingerprint → count, for every
fingerprint asserted more than once). Neither branch
of the ruling permits a duplicate to pass uncounted.
(The point was surfaced from here as a divergence on
adoption and resolved by the ruling as conformance
under branch 2 — recorded in the DESIGN-17 memo.)

## Coverage, published

Every validation run reports: claims, and the non-null
counts for `source`, `falsifier`, and
`does_not_establish`, plus the fingerprint census. CI's
pattern gate runs `pattern-validate` on the program
ledger on every change, so the counts are part of the
standing record. A legacy gap is a standing number —
never silence, never invented content.
