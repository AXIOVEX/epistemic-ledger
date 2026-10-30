"""Scale run (DESIGN-16, claim S7).

At the requested record count, on the chained store: open time
and full-verification rate. Structural impact is measured on
the bench's reference graph (10,000 claims, ~40,000 support
edges — the shape DESIGN-13's own impact budget uses). S7's
numbers are claims set in advance: open within 5 s,
verification at or above 20,000 records/s, structural impact
within 250 ms. The report states each measured value beside
its claim and marks pass or miss as measured; a miss is
revised in the open (a memo amendment), never by editing the
thresholds here after the fact.

Why impact is not measured at the full record count: impact is
a property of the claims graph, not of the log's length.
Building a million-claim Python store to re-measure a graph
property would spend the nightly's budget without changing
what is proven; the report says exactly which store each
number came from. The impact figure is the median of five
timed runs after one warm-up — the bench's own methodology,
adopted after the first nightly's single cold run (406.9 ms)
proved incomparable to the bench's warm medians.

Usage:
    python -m tools.stress.scale --records 1000000 --out report.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

SEED_HEX = "07" * 32
ACTOR = "stress-writer"
OPEN_BUDGET_S = 5.0
VERIFY_BUDGET_RPS = 20_000.0
IMPACT_BUDGET_MS = 250.0
IMPACT_CLAIMS = 10_000


def run_scale(records: int) -> dict:
    from epistemic_ledger._core import RustStore
    from epistemic_ledger.ed25519 import publickey

    pub = publickey(bytes.fromhex(SEED_HEX)).hex()
    tmp = Path(tempfile.mkdtemp(prefix="scale-"))
    store_dir = tmp / "store"

    store = RustStore.open(str(store_dir))
    for i in range(records):
        store.append(
            "2026-01-01T00:00:00Z",
            ACTOR,
            "stress_record",
            json.dumps({"i": i}),
            SEED_HEX,
        )
    del store

    t0 = time.perf_counter()
    store = RustStore.open(str(store_dir))
    open_s = time.perf_counter() - t0

    t0 = time.perf_counter()
    verified = store.verify(json.dumps({ACTOR: pub}), 1)
    verify_s = time.perf_counter() - t0
    del store
    verify_rps = verified / verify_s if verify_s else 0.0

    impact_ms = None
    if records >= 10_000:
        from epistemic_ledger import Ledger

        # The bench's reference graph shape (tools/bench_budgets.py):
        # 10,000 claims, each supported by the claims 1, 7, 31, and
        # 101 places behind it (~40,000 edges).
        led = Ledger(str(tmp / "graph"))
        ids = [led.assert_claim(f"scale-{i}", 0.5) for i in range(IMPACT_CLAIMS)]
        for i in range(1, IMPACT_CLAIMS):
            for back in (1, 7, 31, 101):
                j = i - back
                if j >= 0:
                    led.add_support(
                        ids[i], ids[j], "evidential", p_given=0.9, p_given_not=0.2
                    )
        led.impact(ids[0], max_results=20000)  # warm-up, untimed
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            led.impact(ids[0], max_results=20000)
            times.append((time.perf_counter() - t0) * 1000.0)
        impact_ms = statistics.median(times)
        led.close()

    return {
        "claim": "S7",
        "records": records,
        "open_s": round(open_s, 3),
        "open_budget_s": OPEN_BUDGET_S,
        "open_pass": open_s <= OPEN_BUDGET_S,
        "verify_rps": round(verify_rps, 1),
        "verify_budget_rps": VERIFY_BUDGET_RPS,
        "verify_pass": verify_rps >= VERIFY_BUDGET_RPS,
        "impact_ms": round(impact_ms, 1) if impact_ms is not None else None,
        "impact_runs": 5 if impact_ms is not None else None,
        "impact_claims": IMPACT_CLAIMS if impact_ms is not None else None,
        "impact_budget_ms": IMPACT_BUDGET_MS,
        "impact_pass": (impact_ms <= IMPACT_BUDGET_MS)
        if impact_ms is not None
        else None,
        "passed": open_s <= OPEN_BUDGET_S
        and verify_rps >= VERIFY_BUDGET_RPS
        and (impact_ms is None or impact_ms <= IMPACT_BUDGET_MS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=1_000_000)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    report = run_scale(args.records)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
