"""Reader-concurrency run (DESIGN-16, claim S4).

One writer appending at full rate while N reader processes query
for the run's duration. No reader may ever observe a partial or
torn record: reads return whole, chain-consistent results or
clean errors, and point-read latency stays within a p99 of
250 ms.

Why two surfaces: the Python Ledger is single-writer by design
(DESIGN-12) — opening takes an exclusive lock and LQL executes
through a Ledger object, so N processes cannot each run
led.query against the live store. The run measures the two read
surfaces the architecture actually offers concurrent readers:
the chained store's verified point reads (surface ``rust``), and the
Python projection read through read-only SQLite connections
running the point query LQL's CLAIM compiles to (surface
``sqlite``). The literal LQL-through-Ledger reading of S4 is not
measurable on the single-writer architecture; the nightly notes
record that rather than quietly redefining the claim.
The first nightly ran the rust surface as whole-log reads and
its latency leg failed (p99 760 ms at ~300k records); the
owner chose building the point-read surface over revising the
claim, so the rust surface is now `RustReader` point reads
and S4 stands as written.

Usage:
    python -m tools.stress.readers --surface rust \
        --duration-seconds 120 --readers 8 --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
P99_BUDGET_MS = 250.0


def _wait_for_acks(ack_path: Path, want: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ack_path.exists():
            with open(ack_path, "rb") as f:
                if f.read().count(b"\n") >= want:
                    return
        time.sleep(0.1)
    raise RuntimeError(f"writer did not reach {want} appends in {timeout}s")


def _p99(latencies: list[float]) -> float:
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    idx = min(len(ordered) - 1, int(0.99 * len(ordered)))
    return ordered[idx]


def run_readers(surface: str, duration: float, readers: int) -> dict:
    engine = "rust" if surface == "rust" else "python"
    tmp = Path(tempfile.mkdtemp(prefix=f"readers-{surface}-"))
    store = tmp / "store"
    ack = tmp / "acks.txt"
    ready = tmp / "ready.txt"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    writer = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tools.stress.worker_append",
            "--store",
            str(store),
            "--engine",
            engine,
            "--count",
            "100000000",
            "--ack",
            str(ack),
            "--ready",
            str(ready),
            "--delay-ms",
            "0",
        ],
        env=env,
    )
    try:
        _wait_for_acks(ack, 50)
        procs = []
        outs = []
        for i in range(readers):
            out = tmp / f"reader-{i}.json"
            outs.append(out)
            procs.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "tools.stress.worker_read",
                        "--surface",
                        surface,
                        "--store",
                        str(store),
                        "--out",
                        str(out),
                        "--duration-seconds",
                        str(duration),
                    ],
                    env=env,
                )
            )
        for proc in procs:
            try:
                proc.wait(timeout=duration + 60)
            except subprocess.TimeoutExpired:
                proc.kill()
    finally:
        writer.terminate()
        try:
            writer.wait(timeout=10)
        except subprocess.TimeoutExpired:
            writer.kill()

    queries = 0
    torn = 0
    errors = 0
    latencies: list[float] = []
    for out in outs:
        if not out.exists():
            errors += 1
            continue
        data = json.loads(out.read_text())
        queries += data["queries"]
        torn += data["torn"]
        errors += data["errors"]
        latencies.extend(data["latencies_ms"])
    p99 = _p99(latencies)
    return {
        "claim": "S4",
        "surface": surface,
        "readers": readers,
        "duration_s": duration,
        "queries": queries,
        "torn_observations": torn,
        "errors": errors,
        "p99_ms": round(p99, 3),
        "passed": torn == 0 and errors == 0 and p99 <= P99_BUDGET_MS,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--surface", choices=["rust", "sqlite"], required=True)
    parser.add_argument("--duration-seconds", type=float, default=120.0)
    parser.add_argument("--readers", type=int, default=8)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    report = run_readers(args.surface, args.duration_seconds, args.readers)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
