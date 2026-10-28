"""Migrate a 0.12.0 store into the chained Rust format.

Implements DESIGN-13 section 9 (claim G1). Reads the legacy
``events.jsonl`` in order and appends every event into a Rust-core
store, preserving each event's timestamp, actor, type, and payload
exactly. The migration itself is the new log's first record (type
``migration``, actor ``system``), and a ``migration-map.json`` in
the new store maps every new sequence number to the legacy
``event_id`` it came from.

Honest limits, by design:

- Legacy history is chained but **not signed**: migration attests
  the history as found; it cannot retroactively sign events for
  writers whose keys it does not hold. Signature enforcement
  starts at ``signed_from_seq`` (the first post-migration append),
  recorded in the map and the returned report.
- A 0.12.0 log altered before migration cannot be detected after
  the fact (DESIGN-13 section 9 states this openly).

Requires the compiled core (``epistemic_ledger._core``); raises
ImportError with guidance when it is not installed.
"""

import json
import os
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
            "installed; migration requires it. Install a build of "
            "epistemic-ledger that includes the Rust engine."
        )
    return _core


def migrate_store(src_dir, dst_dir):
    """Migrate the legacy store at ``src_dir`` into a new chained
    store at ``dst_dir``. Returns the migration report dict."""
    core = _require_core()
    src_log = os.path.join(src_dir, "events.jsonl")
    with open(src_log, encoding="utf-8") as f:
        legacy = [json.loads(line) for line in f if line.strip()]
    if os.path.exists(os.path.join(dst_dir, "events.log")):
        raise FileExistsError(
            f"{dst_dir} already holds a chained store; refusing to overwrite"
        )
    store = core.RustStore.open(dst_dir)
    seq_to_legacy: dict[str, Any] = {}
    marker = json.loads(
        store.append(
            legacy[0]["t"] if legacy else "1970-01-01T00:00:00Z",
            "system",
            "migration",
            json.dumps(
                {
                    "source_format": "0.12-jsonl",
                    "legacy_event_count": len(legacy),
                }
            ),
        )
    )
    seq_to_legacy[str(marker["seq"])] = None
    for event in legacy:
        record = json.loads(
            store.append(
                event["t"],
                event["actor"],
                event["type"],
                json.dumps(event["payload"]),
            )
        )
        seq_to_legacy[str(record["seq"])] = event["event_id"]
    signed_from_seq = store.next_seq
    verified = store.verify("{}", 1)
    head = store.head_hash
    del store
    migration_map = {
        "format": 1,
        "source_format": "0.12-jsonl",
        "signed_from_seq": signed_from_seq,
        "seq_to_legacy_event_id": seq_to_legacy,
    }
    with open(os.path.join(dst_dir, "migration-map.json"), "w", encoding="utf-8") as f:
        json.dump(migration_map, f, indent=2)
    return {
        "legacy_events": len(legacy),
        "total_records": verified,
        "head_hash": head,
        "signed_from_seq": signed_from_seq,
        "dst": dst_dir,
    }
