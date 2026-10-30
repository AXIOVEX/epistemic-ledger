"""Mixed soak (DESIGN-16, claim S3).

Two legs run side by side for the soak's duration:

- an append leg — the chained store under a full-rate append
  worker (the DESIGN-13 append budget applies to this engine,
  and the leg must sustain it);
- a mixed leg — one Python Ledger under interleaved asserts,
  score revisions, supports, impact analyses, LQL queries, and
  periodic full verifications.

The soak passes with zero errors on either leg, resident memory
of the mixed process within 10% of its post-warm-up level at the
end, a clean full verification of both stores at the end, and
the append leg at or above budget. The mixed leg's own operation
rates are reported as measured; no budget is invented for them.

Usage:
    python -m tools.stress.soak --duration-seconds 7200 \
        --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APPEND_BUDGET_RPS = 2000.0
WARMUP_CLAIMS = 300


def _rss_kb() -> int | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


def run_soak(duration: float, seed: int | None = None) -> dict:
    from epistemic_ledger import Ledger

    rng = random.Random(seed)
    tmp = Path(tempfile.mkdtemp(prefix="soak-"))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    ack = tmp / "acks.txt"
    ready = tmp / "ready.txt"
    append_store = tmp / "append-store"
    writer = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tools.stress.worker_append",
            "--store",
            str(append_store),
            "--engine",
            "rust",
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

    errors: list[dict] = []
    ops = {"assert": 0, "score": 0, "support": 0, "impact": 0, "query": 0, "verify": 0}
    appends = 0
    final_verify_ok = False
    append_rps = 0.0
    rss_start = None
    rss_end = None
    started = time.monotonic()
    try:
        led = Ledger(str(tmp / "mixed-store"))
        ids: list[str] = []
        for i in range(WARMUP_CLAIMS):
            cid = led.assert_claim(f"soak-warm-{i}", 0.5)
            if ids:
                led.add_support(ids[-1], cid, "evidential", 0.8, 0.3)
            ids.append(cid)
        rss_start = _rss_kb()
        deadline = started + duration
        cycle = 0
        while time.monotonic() < deadline:
            cycle += 1
            try:
                cid = led.assert_claim(f"soak-{cycle}", rng.uniform(0.2, 0.8))
                ids.append(cid)
                ops["assert"] += 1
                target = rng.choice(ids)
                led.manual_score(target, rng.uniform(0.0, 1.0))
                ops["score"] += 1
                if len(ids) > 2:
                    a, b = rng.sample(ids, 2)
                    led.add_support(a, b, "evidential", 0.7, 0.4)
                    ops["support"] += 1
                if cycle % 7 == 0:
                    led.query(f"CLAIM {rng.choice(ids)}")
                    ops["query"] += 1
                if cycle % 20 == 0:
                    led.impact(ids[0], max_results=500)
                    ops["impact"] += 1
                if cycle % 200 == 0:
                    report = led.verify_store()
                    ops["verify"] += 1
                    if not report["ok"]:
                        errors.append(
                            {
                                "cycle": cycle,
                                "error": f"verify_store: {report['problems'][:2]}",
                            }
                        )
            except Exception as exc:  # recorded, never hidden
                errors.append({"cycle": cycle, "error": f"{type(exc).__name__}: {exc}"})
        rss_end = _rss_kb()
        final = led.verify_store()
        final_verify_ok = bool(final["ok"])
        led.close()
    finally:
        elapsed = max(time.monotonic() - started, 0.001)
        writer.terminate()
        try:
            writer.wait(timeout=10)
        except subprocess.TimeoutExpired:
            writer.kill()
        if ack.exists():
            with open(ack, "rb") as f:
                appends = f.read().count(b"\n")
        append_rps = appends / elapsed

    # The append leg's store must verify clean after the kill.
    append_verify_ok = False
    try:
        from epistemic_ledger._core import RustStore
        from epistemic_ledger.ed25519 import publickey

        store = RustStore.open(str(append_store))
        pub = publickey(bytes.fromhex("07" * 32)).hex()
        verified = store.verify(json.dumps({"stress-writer": pub}), 1)
        # The terminated worker may leave one in-flight append
        # beyond the ack frontier — the S1 prefix property.
        append_verify_ok = appends <= verified <= appends + 1
        del store
    except Exception as exc:
        errors.append({"cycle": -1, "error": f"append-leg verify: {exc}"})

    drift = None
    if rss_start and rss_end:
        drift = round(100.0 * (rss_end - rss_start) / rss_start, 2)
    passed = (
        not errors
        and final_verify_ok
        and append_verify_ok
        and append_rps >= APPEND_BUDGET_RPS
        and (drift is None or drift <= 10.0)
    )
    return {
        "claim": "S3",
        "duration_s": duration,
        "ops": ops,
        "errors": errors,
        "rss_start_kb": rss_start,
        "rss_end_kb": rss_end,
        "rss_drift_pct": drift,
        "append_rps": round(append_rps, 1),
        "append_budget_rps": APPEND_BUDGET_RPS,
        "final_verify_ok": final_verify_ok,
        "append_verify_ok": append_verify_ok,
        "passed": passed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-seconds", type=float, default=7200.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    report = run_soak(args.duration_seconds, args.seed)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
