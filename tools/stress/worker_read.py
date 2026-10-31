"""Reader worker for the concurrency run (DESIGN-16, claim S4).

One reader process. It queries its surface in a loop for the
requested duration and records, per query: latency, and whether
the observation was torn — for the chained store, a point read
that returns nothing for an in-range sequence, a record whose
sequence is not the one asked for, or a record missing a field;
for the projection, a row with a score outside [0, 1] or a
missing status. Partial results are written every 25 queries
(write-then-rename) so a killed reader still leaves its
observations behind; the final write lands at duration end.

Surfaces (see tools/stress/readers.py for why there are two):
``rust`` reads the chained store through verified point reads
(a `RustReader`: an offset index over the log, one record per
query, its hash recomputed in the core before it is returned);
``sqlite`` holds a read-only connection to the Python store's
projection and runs the point query LQL's CLAIM compiles to.

Usage:
    python -m tools.stress.worker_read --surface rust \
        --store DIR --out FILE --duration-seconds 120
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_RECORD_FIELDS = {"seq", "t", "actor", "type", "payload", "prev_hash", "hash"}


def _write_out(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def _run_rust(store: str, duration: float, out: Path) -> dict:
    import random

    from epistemic_ledger._core import RustReader

    rng = random.Random()
    reader = RustReader.open(store)
    latencies: list[float] = []
    torn = 0
    errors = 0
    deadline = time.monotonic() + duration
    n = 0
    while time.monotonic() < deadline:
        try:
            # Untimed: keeping the index current is bookkeeping,
            # not the read S4 prices. When the writer has
            # appended, this scans only the new lines.
            reader.refresh()
            count = reader.count
            if count == 0:
                time.sleep(0.01)
                continue
            seq = rng.randint(1, count)
            t0 = time.perf_counter()
            raw = reader.record_json(seq)
            latencies.append((time.perf_counter() - t0) * 1000.0)
            n += 1
            if raw is None:
                torn += 1
            else:
                rec = json.loads(raw)
                if rec.get("seq") != seq or not _RECORD_FIELDS <= set(rec):
                    torn += 1
        except Exception:
            errors += 1
            time.sleep(0.01)
        if n and n % 25 == 0:
            _write_out(
                out,
                {
                    "queries": n,
                    "torn": torn,
                    "errors": errors,
                    "latencies_ms": latencies,
                },
            )
    return {"queries": n, "torn": torn, "errors": errors, "latencies_ms": latencies}


def _run_sqlite(store: str, duration: float, out: Path) -> dict:
    import sqlite3

    db_path = os.path.join(store, "ledger.db")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    latencies: list[float] = []
    torn = 0
    errors = 0
    last_count = 0
    deadline = time.monotonic() + duration
    n = 0
    while time.monotonic() < deadline:
        try:
            t0 = time.perf_counter()
            row = conn.execute(
                "SELECT claim_id, statement, score, status FROM claims "
                "ORDER BY claim_id DESC LIMIT 1"
            ).fetchone()
            if row is not None:
                hit = conn.execute(
                    "SELECT claim_id, statement, score, status FROM claims "
                    "WHERE claim_id = ?",
                    (row["claim_id"],),
                ).fetchone()
                latencies.append((time.perf_counter() - t0) * 1000.0)
                n += 1
                if (
                    hit is None
                    or hit["statement"] is None
                    or hit["status"] is None
                    or not (0.0 <= hit["score"] <= 1.0)
                ):
                    torn += 1
            count = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            if count < last_count:
                torn += 1
            last_count = max(last_count, count)
        except Exception:
            errors += 1
            time.sleep(0.01)
        if n and n % 25 == 0:
            _write_out(
                out,
                {
                    "queries": n,
                    "torn": torn,
                    "errors": errors,
                    "latencies_ms": latencies,
                },
            )
    conn.close()
    return {"queries": n, "torn": torn, "errors": errors, "latencies_ms": latencies}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=["rust", "sqlite"], required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    args = parser.parse_args(argv)

    out = Path(args.out)
    run = _run_rust if args.surface == "rust" else _run_sqlite
    result = run(args.store, args.duration_seconds, out)
    _write_out(out, result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
