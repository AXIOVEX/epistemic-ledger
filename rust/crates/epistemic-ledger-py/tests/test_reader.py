"""Bindings tests for the point-read surface (DESIGN-16, S4).

`RustReader` opens a chained store read-only, indexes it by
byte offset, and serves one verified record per call — the
surface the reader-concurrency leg measures.
"""

from __future__ import annotations

import json

from epistemic_ledger._core import RustReader, RustStore

SEED = "07" * 32
T0 = "2026-01-01T00:00:00+00:00"


def _store(path, n=5):
    store = RustStore.open(str(path))
    for i in range(n):
        store.append(T0, "w", "assert", json.dumps({"i": i}), SEED)
    return store


def test_point_reads_round_trip(tmp_path):
    _store(tmp_path / "s", 5)
    reader = RustReader.open(str(tmp_path / "s"))
    assert reader.count == 5
    for seq in range(1, 6):
        record = json.loads(reader.record_json(seq))
        assert record["seq"] == seq
        assert record["payload"] == {"i": seq - 1}
    assert reader.record_json(0) is None
    assert reader.record_json(6) is None


def test_refresh_follows_a_writer(tmp_path):
    store = _store(tmp_path / "s", 2)
    reader = RustReader.open(str(tmp_path / "s"))
    assert reader.count == 2
    store.append(T0, "w", "assert", json.dumps({"i": 2}), SEED)
    assert reader.refresh() == 3
    assert json.loads(reader.record_json(3))["payload"] == {"i": 2}
    assert reader.head_hash == store.head_hash


def test_reader_on_a_missing_store_is_empty(tmp_path):
    reader = RustReader.open(str(tmp_path / "nope"))
    assert reader.count == 0
    assert reader.record_json(1) is None
