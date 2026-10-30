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
import tempfile
import time

from epistemic_ledger import Ledger
from epistemic_ledger._core import (
    RustStore,
    verify_consistency_json,
    verify_inclusion_json,
    verify_sth_json,
)

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
    print("phase: chained appends (100,000, fsync per record)", flush=True)
    start = time.perf_counter()
    for i in range(n):
        store.append(T0, "w", "note", json.dumps({"i": i}), SEED)
    elapsed = time.perf_counter() - start
    print(f"phase: chained appends done in {elapsed:.1f}s", flush=True)
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

    bench_proofs(path)


def bench_proofs(path):
    """DESIGN-15 stage 1 proof budgets (50 ms) on the 100k chained
    store: 97 complete checkpoints. Generation is measured on a
    warm store (the proof cache computed once, as a serving process
    holding the store open would); the warm-up itself is printed as
    a phase line, not hidden. Verification is the standalone path —
    JSON artifacts and the public key only."""
    from epistemic_ledger import anchors

    store = RustStore.open(path)
    start = time.perf_counter()
    sth_last = store.sth_json(T0, "bench-ck", SEED)
    warm_s = time.perf_counter() - start
    print(f"phase: proof-cache warm-up at 100,000 events took {warm_s:.1f}s", flush=True)
    pubkey = json.loads(_pubkeys())["w"]
    assert verify_sth_json(sth_last, pubkey)

    times = []
    for _ in range(5):
        start = time.perf_counter()
        proof = json.loads(store.inclusion_proof_json(50_000))
        times.append((time.perf_counter() - start) * 1000)
    median_ms = statistics.median(times)
    report("inclusion proof generation (warm, 100k)", median_ms, "<= 50", "ms", median_ms <= 50)

    times = []
    for _ in range(5):
        start = time.perf_counter()
        ok = verify_inclusion_json(
            proof["leaf_hash"],
            proof["index"],
            proof["segment_len"],
            json.dumps(proof["proof"]),
            proof["root"],
        )
        times.append((time.perf_counter() - start) * 1000)
    assert ok
    median_ms = statistics.median(times)
    report("inclusion proof verification (standalone)", median_ms, "<= 50", "ms", median_ms <= 50)

    sth_first = store.sth_json(T0, "bench-ck", SEED, 1)
    consistency = store.consistency_proof_json(1, 97)
    times = []
    for _ in range(5):
        start = time.perf_counter()
        ok = verify_consistency_json(sth_first, sth_last, consistency)
        times.append((time.perf_counter() - start) * 1000)
    assert ok
    median_ms = statistics.median(times)
    report("consistency verification (97 checkpoints)", median_ms, "<= 50", "ms", median_ms <= 50)

    # The pure-Python standalone verifier reaches the same verdicts
    # on the same artifacts (no budget: it is the audit path, not
    # the serving path).
    sth_proof = store.sth_json(T0, "bench-ck", SEED, proof["checkpoint_seq"])
    start = time.perf_counter()
    ok_py = anchors.verify_anchored_record(
        proof["leaf_hash"], proof, json.loads(sth_proof), pubkey
    )
    py_ms = (time.perf_counter() - start) * 1000
    assert ok_py
    print(f"phase: pure-Python anchored-record verification took {py_ms:.1f} ms", flush=True)
    del store


def build_graph_store(tmp):
    path = os.path.join(tmp, "graph")
    led = Ledger(path)
    print("phase: graph asserts (10,000 claims)", flush=True)
    ids = [led.assert_claim(f"claim {i}", 0.5) for i in range(10_000)]
    print("phase: graph edges (~40,000 supports)", flush=True)
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
    # Top the store up to ~100,000 events with revisions of late
    # claims. The back-1 edges form chains, so a revision cascades
    # into further revision events until the movement attenuates
    # below the revisit epsilon; the loop therefore counts events
    # as it goes and stops at the target instead of running a
    # fixed 50,000 iterations (which emitted several times the
    # intended events and made this build take tens of minutes).
    print("phase: graph top-up revisions (to ~100,000 events)", flush=True)
    base_events = len(led._events())
    r = 0
    while base_events < 100_000:
        for _ in range(1_000):
            led.manual_score(ids[9900 + (r % 100)], 0.4 + (r % 10) * 0.01)
            r += 1
        base_events = len(led._events())
    events = base_events
    print(
        f"graph store: {events} events, 10,000 claims, ~40,000 edges",
        flush=True,
    )
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
    report(
        "impact structural (10k-claim graph)",
        median_ms,
        "<= 100",
        "ms",
        median_ms <= 100,
    )

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
