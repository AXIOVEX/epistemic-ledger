"""Allow ``python -m epistemic_ledger`` as the CLI entry point."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
