"""Performance budgets (DESIGN-13 section 8), enforced.

Builds the reference workloads and measures them against the
budgets. A regression past budget fails the build like any other
test: this script exits non-zero and prints the measured numbers
either way, so the release notes can quote them with the hardware
stated.

Workloads:
  append   sustained single-writer appends to a chained store,
           fsync per record (the Rust store's durability default)
  verify   full chain verification of that store, signatures in
           the same pass
  open     chained-store open at 100,000 events
  impact   structural and propagated impact on the reference
           graph (10,000 claims, ~40,000 edges, decision nodes)
  query    LQL point and filtered-set queries on the graph store
           (100,000+ events, 10,000 live claims)

Run: python tools/bench_budgets.py   (needs the built bindings:
the maturin wheel installed, as in the CI bindings job)
"""

import json
import os
import shutil
import statistics
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from epistemic_ledger import Ledger  # noqa: E402
from epistemic_ledger._core import RustStore  # noqa: E402

SEED = "07" * 32
T0 = "2026-01-01T00:00:00+00:00"

RESULTS = []


def report(name, measured, budget, unit, ok):
    RESULTS.append((name, measured, budget, unit, ok))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}: {measured:.1f} {unit} (budget {budget} {unit})")


def _pubkeys():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )

    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(SEED))
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return json.dumps({"w": pub})


def bench_chained(tmp):
    path = os.path.join(tmp, "chained")
    store = RustStore.open(path)
    n = 100_000
    start = time.perf_counter()
    for i in range(n):
        store.append(T0, "w", "note", json.dumps({"i": i}), SEED)
    elapsed = time.perf_counter() - start
    rate = n / elapsed
    report("append (sustained, fsync/record)", rate, ">= 2000", "rec/s", rate >= 2000)

    pubkeys = _pubkeys()
    start = time.perf_counter()
    verified = store.verify(pubkeys, 1)
    elapsed = time.perf_counter() - start
    assert verified == n
    rate = n / elapsed
    report("verify (full chain + signatures)", rate, ">= 50000", "rec/s", rate >= 50000)
    del store

    opens = []
    for _ in range(5):
        start = time.perf_counter()
        again = RustStore.open(path)
        opens.append((time.perf_counter() - start) * 1000)
        del again
    median_open = statistics.median(opens)
    report("open at 100,000 events", median_open, "<= 250", "ms", median_open <= 250)


def build_graph_store(tmp):
    path = os.path.join(tmp, "graph")
    led = Ledger(path)
    ids = [led.assert_claim(f"claim {i}", 0.5) for i in range(10_000)]
    for i in range(1, 10_000):
        for back in (1, 7, 31, 101):
            j = i - back
            if j >= 0:
                led.add_support(
                    ids[i], ids[j], "evidential", p_given=0.9, p_given_not=0.2
                )
    for k in range(200):
        basis = [ids[(k * 37 + d * 11) % 1000] for d in range(5)]
        led.record_decision(f"decision {k}", list(dict.fromkeys(basis)))
    # Top the store up to ~100,000 events with revisions of
    # late claims (small dependent sets, so this stays cheap).
    for r in range(50_000):
        led.manual_score(ids[9900 + (r % 100)], 0.4 + (r % 10) * 0.01)
    events = len(led._events())
    print(f"graph store: {events} events, 10,000 claims, ~40,000 edges")
    return led, ids


def bench_graph(tmp):
    led, ids = build_graph_store(tmp)
    root = ids[0]

    times = []
    for _ in range(5):
        start = time.perf_counter()
        result = led.impact(root, max_results=20000)
        times.append((time.perf_counter() - start) * 1000)
    assert len(result["nodes"]) > 9000  # the closure is the graph
    median_ms = statistics.median(times)
    report("impact structural (10k-claim graph)", median_ms, "<= 100", "ms", median_ms <= 100)

    times = []
    for _ in range(3):
        start = time.perf_counter()
        led.impact(root, mode="propagated", revised_score=0.0)
        times.append((time.perf_counter() - start) * 1000)
    median_ms = statistics.median(times)
    report("impact propagated (dry run)", median_ms, "<= 500", "ms", median_ms <= 500)

    times = []
    for _ in range(5):
        start = time.perf_counter()
        led.query(f"CLAIM {ids[5000]}")
        times.append((time.perf_counter() - start) * 1000)
    median_ms = statistics.median(times)
    report("LQL point query", median_ms, "<= 50", "ms", median_ms <= 50)

    times = []
    for _ in range(5):
        start = time.perf_counter()
        rows = led.query("CLAIMS WHERE score > 0.45 AND status = 'active'")
        times.append((time.perf_counter() - start) * 1000)
    assert rows
    median_ms = statistics.median(times)
    report("LQL filtered-set query", median_ms, "<= 50", "ms", median_ms <= 50)
    led.close()


def main():
    tmp = tempfile.mkdtemp(prefix="epistemic-ledger-bench-")
    try:
        bench_chained(tmp)
        bench_graph(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [r for r in RESULTS if not r[4]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} budgets met")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
