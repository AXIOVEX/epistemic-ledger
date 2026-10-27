# Contributing

Thanks for looking. This is a small research-grade project; the rules
are simple:

1. **Tests first for behavior changes.** The test suite is the contract:
   `python -m pytest` from the repo root must stay green, coverage
   floors (see `pyproject.toml` / CI) must hold, and new behavior in
   the scoring core needs a property test where an invariant exists.
2. **Plain language.** Docs and comments use plain US English; a
   technical term is defined in plain words at first use.
3. **Measured claims only.** Performance or accuracy claims in docs
   need a report under `docs/` produced by a script under
   `prototype/validation/`, the same discipline the existing results
   follow.
4. **Checks.** Run `ruff check .`, `ruff format --check .`,
   `mypy src/epistemic_ledger`, and `mkdocs build --strict` before
   opening a pull request; CI runs the same gates.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,docs]"
python -m pytest
epistemic-ledger demo
```
