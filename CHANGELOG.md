# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- The interface layer (DESIGN-13 sections 5–6): LQL, a small
  read-only query language over the core (`Ledger.query`, grammar
  in docs/lql.md — every construct returns exactly the
  corresponding core API result; malformed input is a parse error
  naming the position and executes nothing); an MCP server
  (`epistemic-ledger-mcp`, stdio JSON-RPC, standard library only)
  with twelve typed tools whose write tools pass through the same
  governed paths as the API; and the CLI commands `impact`,
  `query`, `health`, `snapshot`, and `restore` joining `demo`,
  `verify`, `kill-metrics`, and `migrate`. A three-face scenario
  in CI diffs the API, CLI, and MCP results (claim M1). Also:
  `Ledger.get_claim`, `Ledger.list_claims`, `Ledger.health()`,
  and `Ledger.verify(deep=True)` (base store verification plus a
  signed-verdict audit). Note: AS_OF is defined for CLAIM, CLAIMS,
  EVENTS, and DECISIONS; graph traversals stay current-state, and
  AS_OF before them is a parse error rather than a silent
  substitution.
- Snapshots and restore (DESIGN-13 section 4): a chained store
  can be written as a self-contained bundle (the log plus a
  manifest whose hash covers the bundle, format in
  `rust/SNAPSHOT-FORMAT.md`), verified from the bundle alone, and
  restored into a new store — the restore verifies the bundle
  completely before writing anything, then re-validates the
  restored chain against the manifest. Rust core
  (`snapshot` module), Python bindings (`snapshot_json`,
  `verify_snapshot_json`, `restore_snapshot_json`), and the
  `epistemic_ledger.snapshots` wrapper. The restore drill runs in
  CI with the bindings tests, including on a migrated store with
  the original deleted.
- Impact analysis (DESIGN-13 section 3): `Ledger.impact(claim_id,
  mode)` answers "if this claim falls, what else moves, and which
  decisions were made on top of it?" Structural mode returns the
  transitive closure of dependents — derived claims and decision
  nodes — with graph distances and the paths each node was reached
  by. Propagated mode dry-runs a revision (to a stated score, or to
  zero by default) on a throwaway copy of the store, using the
  ordinary revision machinery, and reports every score movement
  plus the decisions resting on moved ground. Depth and result
  caps are reported in the result whenever they bind, never
  silently applied.
- Decision nodes: `Ledger.record_decision(label, basis, ...)`
  records a decision with the immutable set of claims it rested
  on; `Ledger.decisions()` lists them, including the governance
  acts already in the log (contradiction holds, dismissals,
  resolutions), whose named claim references become their basis
  sets.

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
