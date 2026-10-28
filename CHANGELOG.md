# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

Hardening items 1-3 from the Ledger Standard v1 gap assessment.

### Added

- `verify_store()` now also checks the projection-to-log direction:
  a projection claim row (or a claim id referenced by the other
  claim-scoped tables) with no corresponding assert event in the log
  is reported. Its result gains a `projection_checked` count, and a
  claim the log moves to a terminal lifecycle status is expected to
  have no live row rather than reported as missing one.
- `Ledger.audit_writer_pubkey(writer_id, t)`: the writer key in
  force at a past time, from the bitemporal writers table.
- Claim lifecycle statuses `entered-in-error` and `dead`, set with
  the new `Ledger.set_claim_status()`; the status change is an event
  in the log. `CLAIM_STATUSES` and `TERMINAL_STATUSES` are exported
  from the package root.

### Changed

- `verify_verdict_signatures()` now verifies each signed verdict
  against the key in force at its signing time instead of the
  signer's current key. Key rotation no longer invalidates verdicts
  signed before the rotation, and a verdict signed with a key that
  was not in force at its signing time fails the audit.
- Breaking: `Ledger.supersede()` now requires the reason bundle —
  `reason` and `source` as required keyword arguments, alongside the
  existing `actor`. The bundle is recorded on the supersede event,
  and `set_claim_status()` requires the same bundle.

## [0.12.0] - 2026-10-27

First release on PyPI.

### Added

- Proper Python package: `pip install epistemic-ledger`, import name
  `epistemic_ledger`, source layout under `src/epistemic_ledger/`.
- Command-line interface: `epistemic-ledger demo`, `verify`, and
  `kill-metrics`, also runnable as `python -m epistemic_ledger`.
- Public API re-exported from the package root (`Ledger`, `jeffrey`,
  `dempster_combine`, `interval_to_mass`, and the shared constants),
  plus a `py.typed` marker.
- Documentation site (MkDocs) with a getting-started guide, a concepts
  guide, and an API reference generated from docstrings; ReadTheDocs
  configuration.
- Continuous integration: lint, format, and type-check gates; a test
  matrix across supported Python versions and operating systems;
  coverage with enforced floors; a strict docs build; a package build
  checked with `twine`.
- Property-based tests (Hypothesis) for the scoring invariants, plus
  CLI and round-trip tests.
- `CHANGELOG.md`, `CONTRIBUTING.md`, and `SECURITY.md`.

### Changed

- Code license is now MIT. The framing paper, design memos, and
  research documents under `docs/` remain all rights reserved
  (see `LICENSE-DOCS.txt` and `NOTICE.md`).
- The prototype modules moved from `prototype/` into the package.
  Thin compatibility shims remain under `prototype/` so the research
  scripts there keep working with the package installed.

### Removed

- The standalone `prototype/pyproject.toml` (the package named
  `axiovex-ledger` that was never published) and the committed
  `egg-info` build artifacts.

## [0.11.1] - 2026-10-09 and earlier

The research prototype line, developed in this repository under
`prototype/` before the PyPI packaging. Highlights, each with its full
report under `docs/`:

- Event-sourced bitemporal ledger with a dependency-propagated revisit
  loop, learned entrenchment, Dempster–Shafer intervals, joint
  likelihoods, contradiction detection and resolution, governance
  (writer tiers, signed verdicts, escalation, named-graph authority
  ceilings, predicate policies), an offline LLM consolidation pass,
  and a hardened single-writer store with replay verification.
- 0.11.1: manual scores now propagate through the revisit loop
  (OVERRIDE-CAL-01).

[0.12.0]: https://github.com/AXIOVEX/epistemic-ledger/releases/tag/v0.12.0
