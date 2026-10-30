"""Append worker for the kill-point sweep (DESIGN-16, claim S1).

Appends numbered records to a store as fast as it can (with a small
configurable pause, to vary where a kill lands). After each append
RETURNS — for the Rust store that means the record was written, synced,
and read back (DESIGN-14); for the Python engine it means the verified
append and the projection update completed — the worker records the
record's index in the ack file with an unbuffered, fsynced write. The
ack file is the ground truth of what the store acknowledged; the parent
kills this process at a random moment and checks what survived.

Usage:
    python -m tools.stress.worker_append --store DIR --engine rust \
        --count 10000 --ack FILE --ready FILE [--delay-ms 1.0]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

SEED_HEX = "07" * 32  # fixed test signing seed (same as the bindings tests)
ACTOR = "stress-writer"


def _ack(ack_fd: int, index: int) -> None:
    os.write(ack_fd, f"{index}\n".encode())
    os.fsync(ack_fd)


def run_rust(store_dir: str, count: int, ack_fd: int, delay_s: float) -> None:
    from epistemic_ledger._core import RustStore

    store = RustStore.open(store_dir)
    for i in range(count):
        store.append(
            "2026-01-01T00:00:00Z",
            ACTOR,
            "stress_record",
            json.dumps({"i": i}),
            SEED_HEX,
        )
        _ack(ack_fd, i)
        if delay_s:
            time.sleep(delay_s)


def run_python(store_dir: str, count: int, ack_fd: int, delay_s: float) -> None:
    from epistemic_ledger import Ledger

    ledger = Ledger(store_dir)
    for i in range(count):
        ledger.assert_claim(f"stress-{i}", 0.5, actor=ACTOR)
        _ack(ack_fd, i)
        if delay_s:
            time.sleep(delay_s)
    ledger.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", required=True)
    parser.add_argument("--engine", choices=["rust", "python"], required=True)
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--ack", required=True)
    parser.add_argument("--ready", required=True)
    parser.add_argument("--delay-ms", type=float, default=1.0)
    args = parser.parse_args(argv)

    os.makedirs(args.store, exist_ok=True)
    ack_fd = os.open(args.ack, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        # Signal readiness only once the store is open: store creation
        # itself is not part of the kill window.
        if args.engine == "rust":
            from epistemic_ledger._core import RustStore

            RustStore.open(args.store)
        else:
            from epistemic_ledger import Ledger

            Ledger(args.store).close()
        with open(args.ready, "w") as fh:
            fh.write("ready\n")
        run = run_rust if args.engine == "rust" else run_python
        run(args.store, args.count, ack_fd, args.delay_ms / 1000.0)
    finally:
        os.close(ack_fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
