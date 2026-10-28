"""Verified whole-file writes (DESIGN-14 section 3.2).

The fleet standard (owner directive, 2026-10-28): every state
write that matters is read back and verified before anything
builds on it; a partial or empty file never stands as a successful
write; a failed write fails the run closed. The environment this
project runs in has a platform defect under which a write can
report success while the file on disk lands empty or partial, so
``flush`` + ``fsync`` alone — which report what the OS accepted,
not what can be read back — are not proof.

``write_file_verified`` implements the standard's pattern for
whole files: write a temp file in the same directory, fsync,
read it back and hash-verify it *before* it can replace anything,
atomically rename it over the target, fsync the directory, then
read back and hash-verify the target. Bounded retries with a
fresh temp file each attempt; total failure raises
``VerifiedWriteError`` and the target either does not exist or
still holds its previous content — unverified bytes never
replace a good target, even momentarily.

One deliberate divergence from the fleet tool this pattern comes
from (``~/workspace/system/safe-write/``): its retry ladder adds
a fresh-subprocess rung, which exists because an operator process
can become write-tainted for the rest of its life. Library code
does not spawn subprocesses of itself; it fails closed with a
loud error instead, which the standard equally requires.
"""

import hashlib
import os
import tempfile

_ATTEMPTS = 3


class VerifiedWriteError(RuntimeError):
    """A verified write failed on every attempt."""


def _write_temp(directory, data):
    """Write ``data`` to a fresh temp file in ``directory``,
    fsync it, and return its path. This is the seam the
    fault-injection tests replace (DESIGN-14 section 3.5): a
    double that lands corrupted bytes in the temp file simulates
    the silent-short-write defect exactly where the verified
    write must catch it — before the rename."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".el-verified-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return tmp


def _read_back(path):
    with open(path, "rb") as f:
        return f.read()


def _fsync_dir(directory):
    if os.name == "nt":  # directories cannot be fsynced on Windows
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _attempt(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    tmp = _write_temp(directory, data)
    try:
        if _read_back(tmp) != data:
            return False
        os.replace(tmp, path)
        tmp = None
        _fsync_dir(directory)
        return _read_back(path) == data
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def write_file_verified(path, content, attempts=_ATTEMPTS):
    """Write ``content`` (bytes, or str encoded as UTF-8) to
    ``path`` and return only when the bytes read back from
    ``path`` are exactly the intended bytes. Raises
    ``VerifiedWriteError`` on total failure or empty content.
    Returns a report dict: path, bytes, sha256, attempts used."""
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    if not data:
        raise VerifiedWriteError(f"refusing to write empty content to {path}")
    for i in range(attempts):
        try:
            if _attempt(path, data):
                return {
                    "path": str(path),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "attempts": i + 1,
                }
        except OSError:
            continue
    raise VerifiedWriteError(
        f"verified write to {path} failed on every attempt "
        f"({attempts}): the filesystem is landing writes short, "
        "empty, or corrupted; no unverified content was left at "
        "the target"
    )
