# Prototype directory — research scripts and compatibility shims

The ledger code itself moved into the installable package at
`src/epistemic_ledger/` in the repository root (v0.12.0):

```bash
pip install epistemic-ledger      # or, from a checkout: pip install -e .
from epistemic_ledger import Ledger
```

What stays here:

- The top-level modules (`ledger.py`, `consolidation.py`, `policies.py`,
  `elicit.py`, `ed25519.py`) are thin **compatibility shims** that
  re-export the package, so the research scripts below — which import
  them by their old flat names — keep working with the package
  installed.
- `validation/`, `stress/`, and `context/` are the research harnesses
  that produced the measured results reported in `docs/`. They are
  part of the research record, not the shipped package, and some need
  local models or data that are not in this repository.
- `demo.py` is the original end-to-end scenario; the packaged form is
  `epistemic-ledger demo`.

Historical note: the v0.1 scope this directory originally implemented
(Design Memo 01 §8) — append-only JSONL event log, SQLite bitemporal
claim table, Jeffrey-update revisit loop with early cutoff, the four
queries, and the five kill criteria — is unchanged in the package.
