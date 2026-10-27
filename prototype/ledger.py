"""Compatibility shim — the code moved to the ``epistemic_ledger`` package.

Kept so the research scripts under ``prototype/`` (validation, stress,
context) and older imports (``from ledger import Ledger``) keep working
when the package is installed (``pip install -e .`` from the repo root).
New code should import from ``epistemic_ledger`` directly.
"""
import epistemic_ledger.ledger as _m

globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__")})
