"""Development shim for the Rust bindings crate.

The real package lives in ``src/epistemic_ledger``; this shim exists
only so maturin places the compiled ``_core`` module inside an
``epistemic_ledger`` package in the bindings wheel. When the real
package is installed after the bindings wheel (as the CI bindings
job does), this file is replaced by the real ``__init__`` and the
compiled ``_core`` module stays in place beside it.
"""
