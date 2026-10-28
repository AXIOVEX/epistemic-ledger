"""Snapshots of chained stores (DESIGN-13 section 4).

A snapshot is a self-contained bundle — the chained log plus a
manifest whose hash covers the bundle — that verifies on its own
and restores into a new store without the original. Claims R1/R2:
a restored store is indistinguishable from the original at the
snapshot's sequence number (same chain head, same verification),
and a bundle with one altered byte fails its own verification
before any restore begins.

The bundle layout is specified in rust/SNAPSHOT-FORMAT.md.
Requires the compiled core (``epistemic_ledger._core``); raises
ImportError with guidance when it is not installed.
"""

import json
from typing import Any

_core: Any = None
try:
    from . import _core as _imported_core  # type: ignore[attr-defined]

    _core = _imported_core
except ImportError:  # pragma: no cover - exercised only without the wheel
    pass


def _require_core():
    if _core is None:
        raise ImportError(
            "the compiled Rust core (epistemic_ledger._core) is not "
            "installed; snapshots require it. Install a build of "
            "epistemic-ledger that includes the Rust engine."
        )
    return _core


def snapshot_store(store_dir, bundle_dir):
    """Write a snapshot bundle of the chained store at
    ``store_dir`` into ``bundle_dir``. The store is fully verified
    first, and the finished bundle is verified before this returns.
    Returns the snapshot report dict."""
    core = _require_core()
    return json.loads(core.snapshot_json(str(store_dir), str(bundle_dir)))


def verify_snapshot(bundle_dir):
    """Verify the bundle at ``bundle_dir`` from the bundle alone.
    Returns the snapshot report dict; raises RuntimeError on any
    mismatch."""
    core = _require_core()
    return json.loads(core.verify_snapshot_json(str(bundle_dir)))


def restore_snapshot(bundle_dir, dst_dir):
    """Restore the bundle at ``bundle_dir`` into a new chained
    store at ``dst_dir``. The bundle is verified before anything
    is written. Returns the snapshot report dict."""
    core = _require_core()
    return json.loads(core.restore_snapshot_json(str(bundle_dir), str(dst_dir)))
