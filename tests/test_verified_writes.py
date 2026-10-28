"""Fault-injection tests for DESIGN-14 (verified writes).

The defect these tests simulate is real and observed in this
project's environment: a write that reports success while the
file on disk lands short, empty, or corrupted. Each test replaces
a write seam with a double that lands mangled bytes *while
returning normally* — the defect's exact signature — and checks
the DESIGN-14 claims:

- W1: an event `_emit` returns from is in the log byte-for-byte;
  under a persistent fault the append raises and the log is
  byte-identical to before the call.
- W3: a whole file written through `write_file_verified` holds
  exactly the intended bytes when the call returns, or the call
  raises and the target keeps its previous content (or absence).
"""

import hashlib
import json
import os

import pytest

from epistemic_ledger import _verified
from epistemic_ledger import ledger as ledger_mod
from epistemic_ledger.ledger import Ledger


# ------------------------------------------------------------------
# doubles
# ------------------------------------------------------------------
def _mangle_half(data):
    return data[: len(data) // 2]


def _mangle_zero(data):
    return b""


def _mangle_garbage(data):
    return b"X" * len(data)


MANGLES = [_mangle_half, _mangle_zero, _mangle_garbage]


# ------------------------------------------------------------------
# W3 — whole-file verified writes (_verified.write_file_verified)
# ------------------------------------------------------------------
@pytest.mark.parametrize("mangle", MANGLES)
def test_verified_write_survives_transient_fault(tmp_path, monkeypatch, mangle):
    real = _verified._write_temp
    calls = {"n": 0}

    def flaky(directory, data):
        calls["n"] += 1
        if calls["n"] == 1:
            return real(directory, mangle(data))
        return real(directory, data)

    monkeypatch.setattr(_verified, "_write_temp", flaky)
    target = tmp_path / "state.json"
    report = _verified.write_file_verified(str(target), b'{"ok": true}')
    assert target.read_bytes() == b'{"ok": true}'
    assert report["attempts"] == 2
    assert report["sha256"] == hashlib.sha256(b'{"ok": true}').hexdigest()
    # no temp residue
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


@pytest.mark.parametrize("mangle", MANGLES)
def test_verified_write_persistent_fault_preserves_target(
    tmp_path, monkeypatch, mangle
):
    real = _verified._write_temp
    monkeypatch.setattr(
        _verified, "_write_temp", lambda directory, data: real(directory, mangle(data))
    )
    target = tmp_path / "state.json"
    target.write_bytes(b"previous verified content")
    with pytest.raises(_verified.VerifiedWriteError):
        _verified.write_file_verified(str(target), b"new content")
    assert target.read_bytes() == b"previous verified content"
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_verified_write_persistent_fault_creates_nothing(tmp_path, monkeypatch):
    real = _verified._write_temp
    monkeypatch.setattr(
        _verified,
        "_write_temp",
        lambda directory, data: real(directory, _mangle_half(data)),
    )
    target = tmp_path / "absent.json"
    with pytest.raises(_verified.VerifiedWriteError):
        _verified.write_file_verified(str(target), b"content")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_verified_write_refuses_empty(tmp_path):
    with pytest.raises(_verified.VerifiedWriteError):
        _verified.write_file_verified(str(tmp_path / "x.json"), b"")
    assert not (tmp_path / "x.json").exists()


def test_verified_write_unwritable_directory_fails_closed(tmp_path):
    with pytest.raises(_verified.VerifiedWriteError):
        _verified.write_file_verified(str(tmp_path / "no-such-dir" / "x.json"), b"data")


def test_verified_write_fsync_failure_cleans_up(tmp_path, monkeypatch):
    def boom(fd):
        raise OSError("injected fsync failure")

    monkeypatch.setattr(os, "fsync", boom)
    target = tmp_path / "x.json"
    with pytest.raises(_verified.VerifiedWriteError):
        _verified.write_file_verified(str(target), b"data")
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []  # temp files cleaned up


# ------------------------------------------------------------------
# W1 — verified event appends (ledger._append_verified / _emit)
# ------------------------------------------------------------------
def _raw_land(path, data):
    with open(path, "ab") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


@pytest.mark.parametrize("mangle", MANGLES)
def test_append_verified_transient_fault(tmp_path, monkeypatch, mangle):
    real = ledger_mod._raw_append
    calls = {"n": 0}

    def flaky(path, data):
        calls["n"] += 1
        if calls["n"] == 1:
            _raw_land(path, mangle(data))
        else:
            real(path, data)

    monkeypatch.setattr(ledger_mod, "_raw_append", flaky)
    log = tmp_path / "events.jsonl"
    log.write_bytes(b'{"seed": 0}\n')
    ledger_mod._append_verified(str(log), b'{"a": 1}\n')
    # exactly once, byte-exact, seed untouched
    assert log.read_bytes() == b'{"seed": 0}\n{"a": 1}\n'


@pytest.mark.parametrize("mangle", MANGLES)
def test_append_verified_persistent_fault_changes_nothing(
    tmp_path, monkeypatch, mangle
):
    monkeypatch.setattr(
        ledger_mod, "_raw_append", lambda path, data: _raw_land(path, mangle(data))
    )
    log = tmp_path / "events.jsonl"
    log.write_bytes(b'{"seed": 0}\n')
    with pytest.raises(OSError):
        ledger_mod._append_verified(str(log), b'{"a": 1}\n')
    assert log.read_bytes() == b'{"seed": 0}\n'


def test_ledger_open_survives_transient_append_fault(tmp_path, monkeypatch):
    """End to end through _emit: opening a fresh Ledger emits the
    default-policy event. With the first append landing at half
    length, open must still succeed — the verified append rolled
    back and retried — and the resulting store verifies."""
    real = ledger_mod._raw_append
    calls = {"n": 0}

    def flaky(path, data):
        calls["n"] += 1
        if calls["n"] == 1:
            _raw_land(path, _mangle_half(data))
        else:
            real(path, data)

    monkeypatch.setattr(ledger_mod, "_raw_append", flaky)
    led = Ledger(str(tmp_path / "store"))
    try:
        assert led.verify_store()["ok"]
    finally:
        led.close()
    lines = (tmp_path / "store" / "events.jsonl").read_bytes().splitlines()
    assert lines  # the policy event landed, exactly and parseably
    for line in lines:
        json.loads(line)


def test_append_verified_log_shrinks_mid_append(tmp_path, monkeypatch):
    """Rollback honesty, shape one: if the log ends up SHORTER
    than before the append, there is nothing safe to truncate
    back to. The append must fail immediately and loudly, saying
    the tail must be treated as torn — never retry over a log
    whose prior contents are gone."""

    def shrink(path, data):
        with open(path, "wb") as f:
            f.write(b"")
            f.flush()
            os.fsync(f.fileno())

    monkeypatch.setattr(ledger_mod, "_raw_append", shrink)
    log = tmp_path / "events.jsonl"
    log.write_bytes(b'{"seed": 0}\n')
    with pytest.raises(OSError, match="treated as torn"):
        ledger_mod._append_verified(str(log), b'{"a": 1}\n')


def test_append_verified_log_vanishes_mid_append(tmp_path, monkeypatch):
    """Rollback honesty, shape two: the read-back itself hits an
    OSError (here the file is simply gone). That is a failed
    verification, the rollback fails with it, and the error says
    so — never a silent pass."""

    def vanish(path, data):
        _raw_land(path, data)
        os.unlink(path)

    monkeypatch.setattr(ledger_mod, "_raw_append", vanish)
    log = tmp_path / "events.jsonl"
    log.write_bytes(b'{"seed": 0}\n')
    with pytest.raises(OSError, match="treated as torn"):
        ledger_mod._append_verified(str(log), b'{"a": 1}\n')


def test_verified_write_accepts_str_content(tmp_path):
    target = tmp_path / "s.json"
    _verified.write_file_verified(str(target), "text content")
    assert target.read_bytes() == b"text content"


def test_ledger_open_fails_closed_under_persistent_append_fault(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ledger_mod,
        "_raw_append",
        lambda path, data: _raw_land(path, _mangle_zero(data)),
    )
    with pytest.raises(OSError):
        Ledger(str(tmp_path / "store"))
    log = tmp_path / "store" / "events.jsonl"
    assert not log.exists() or log.read_bytes() == b""
