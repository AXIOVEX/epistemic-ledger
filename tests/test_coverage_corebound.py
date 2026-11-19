"""Coverage for the core-bound wrappers and the entry shim.

These modules (``migrate``, ``snapshots``, ``__main__``) were
previously omitted from the coverage report. The success paths need
the compiled Rust core and skip cleanly without it (the CI coverage
job builds the core, so they run and are measured there); the
no-core error paths run everywhere.
"""

import runpy
import sys

import pytest

import epistemic_ledger.migrate as migrate_mod
import epistemic_ledger.snapshots as snapshots_mod

core = pytest.importorskip("epistemic_ledger._core")


def test_main_module_import_does_not_run():
    import epistemic_ledger.__main__  # noqa: F401


def test_main_module_entrypoint(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["epistemic-ledger", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("epistemic_ledger.__main__", run_name="__main__")
    assert excinfo.value.code == 0


def test_migrate_require_core_missing(monkeypatch):
    monkeypatch.setattr(migrate_mod, "_core", None)
    with pytest.raises(ImportError, match="compiled Rust core"):
        migrate_mod.migrate_store("src", "dst")


def test_snapshots_require_core_missing(monkeypatch):
    monkeypatch.setattr(snapshots_mod, "_core", None)
    for fn in (
        snapshots_mod.snapshot_store,
        snapshots_mod.verify_snapshot,
        snapshots_mod.restore_snapshot,
    ):
        with pytest.raises(ImportError, match="compiled Rust core"):
            fn("a", "b") if fn is not snapshots_mod.verify_snapshot else fn("a")


def _build_chained_store(path, n=5):
    store = core.RustStore.open(str(path))
    for i in range(n):
        store.append(
            "2026-10-27T00:00:00Z",
            "alice",
            "assert",
            f'{{"claim_id": "c{i}"}}',
        )
    head = store.head_hash
    del store
    return head


def test_snapshot_round_trip(tmp_path):
    src = tmp_path / "store"
    bundle = tmp_path / "bundle"
    restored = tmp_path / "restored"
    head = _build_chained_store(src)
    report = snapshots_mod.snapshot_store(str(src), str(bundle))
    assert report["head_hash"] == head
    verified = snapshots_mod.verify_snapshot(str(bundle))
    assert verified["head_hash"] == head
    out = snapshots_mod.restore_snapshot(str(bundle), str(restored))
    assert out["head_hash"] == head


def test_migrate_empty_legacy_store(tmp_path):
    src = tmp_path / "legacy"
    src.mkdir()
    (src / "events.jsonl").write_text("", encoding="utf-8")
    dst = tmp_path / "chained"
    report = migrate_mod.migrate_store(str(src), str(dst))
    assert report["legacy_events"] == 0
    assert report["total_records"] == 1
    assert report["signed_from_seq"] == 2
    assert (dst / "migration-map.json").exists()


def test_migrate_refuses_existing_chained_store(tmp_path):
    src = tmp_path / "legacy"
    src.mkdir()
    (src / "events.jsonl").write_text("", encoding="utf-8")
    dst = tmp_path / "chained"
    migrate_mod.migrate_store(str(src), str(dst))
    with pytest.raises(FileExistsError, match="already holds a chained store"):
        migrate_mod.migrate_store(str(src), str(dst))
