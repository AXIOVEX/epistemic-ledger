"""Development package shim for the bindings crate.

In the shipped package this directory is the real
``epistemic_ledger`` package; here it exists so maturin can place
``_core`` under the ``epistemic_ledger`` namespace during
bindings development and CI.
"""
