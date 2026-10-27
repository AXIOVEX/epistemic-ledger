# Changelog

All notable changes to this project are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project follows [Semantic Versioning](https://semver.org/).

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
