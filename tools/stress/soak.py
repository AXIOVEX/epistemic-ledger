"""Mixed soak (DESIGN-16, claim S3).

Two legs run side by side for the soak's duration:

- an append leg — the chained store under a full-rate append
  worker (the DESIGN-13 append budget applies to this engine,
  and the leg must sustain it). The append store ROTATES every
  30 minutes: the worker is stopped, its segment verified, and
  a fresh store started. Rotation is what the first nightly
  taught: an unbounded 2-hour append leg heads toward ~18M
  records with a full verification of that store still owed at
  the end, and the platform cancelled the step before the
  report was written. Segments bound every verification, and
  the leg keeps its headroom.
- a mixed leg — one Python Ledger under interleaved asserts,
  score revisions, supports, impact analyses, LQL queries, and
  periodic full verifications (on a time cadence: a
  cycle-count cadence makes each verification's cost grow with
  the store it is checking).

The soak passes with zero errors on either leg, resident
memory retained after the mixed ledger closes returning to
within a stated slack of its post-warm-up level (end-of-run
resident size on a growing store is the allocator's
high-water mark, not retained memory — the release-tier
soak runs of 2026-10-31 and the DESIGN-16 notes carry the
evidence), a clean full verification of the mixed store and of every
append segment at the end, and the append leg at or above
budget. The mixed leg's own operation rates are reported as
measured; no budget is invented for them.

Usage:
    python -m tools.stress.soak --duration-seconds 7200 \
        --out report.json
"""

from __future__ import annotations

import argparse
import ctypes
import gc
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
ROTATE_SECONDS = 1800.0
VERIFY_EVERY_SECONDS = 600.0


def _rss_kb() -> int | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


class _AppendLeg:
    """The full-rate append worker, rotated on a clock.

    Each segment is a fresh store directory. Stopping a segment
    verifies it: the verified record count must sit within the
    S1 prefix tolerance of the segment's ack count (the acked
    appends, plus at most the one in flight when the worker was
    stopped).
    """

    def __init__(self, tmp: Path, env: dict) -> None:
        self._tmp = tmp
        self._env = env
        self.segments = 0
        self.appends = 0
        self.all_verified = True
        self._proc: subprocess.Popen | None = None
        self._ack: Path | None = None
        self._store: Path | None = None
        self._segment_started = 0.0

    def _start_segment(self) -> None:
        self.segments += 1
        self._store = self._tmp / f"append-store-{self.segments}"
        self._ack = self._tmp / f"acks-{self.segments}.txt"
        ready = self._tmp / f"ready-{self.segments}.txt"
        self._proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tools.stress.worker_append",
                "--store",
                str(self._store),
                "--engine",
                "rust",
                "--count",
                "100000000",
                "--ack",
                str(self._ack),
                "--ready",
                str(ready),
                "--delay-ms",
                "0",
            ],
            env=self._env,
        )
        self._segment_started = time.monotonic()

    def _stop_segment(self) -> None:
        assert (
            self._proc is not None and self._ack is not None and self._store is not None
        )
        self._proc.terminate()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        acked = 0
        if self._ack.exists():
            with open(self._ack, "rb") as f:
                acked = f.read().count(b"\n")
        self.appends += acked
        try:
            from epistemic_ledger._core import RustStore
            from epistemic_ledger.ed25519 import publickey

            store = RustStore.open(str(self._store))
            pub = publickey(bytes.fromhex("07" * 32)).hex()
            verified = store.verify(json.dumps({"stress-writer": pub}), 1)
            del store
            if not (acked <= verified <= acked + 1):
                self.all_verified = False
        except Exception:
            self.all_verified = False
        self._proc = None

    def start(self) -> None:
        self._start_segment()

    def maybe_rotate(self) -> None:
        if time.monotonic() - self._segment_started >= ROTATE_SECONDS:
            self._stop_segment()
            self._start_segment()

    def finish(self) -> None:
        if self._proc is not None:
            self._stop_segment()


def run_soak(duration: float, seed: int | None = None) -> dict:
    from epistemic_ledger import Ledger

    rng = random.Random(seed)
    tmp = Path(tempfile.mkdtemp(prefix="soak-"))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    leg = _AppendLeg(tmp, env)
    leg.start()

    errors: list[dict] = []
    ops = {"assert": 0, "score": 0, "support": 0, "impact": 0, "query": 0, "verify": 0}
    final_verify_ok = False
    rss_start = None
    rss_end = None
    rss_quiescent = None
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
        last_verify = time.monotonic()
        cycle = 0
        while time.monotonic() < deadline:
            cycle += 1
            leg.maybe_rotate()
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
                if time.monotonic() - last_verify >= VERIFY_EVERY_SECONDS:
                    report = led.verify_store()
                    ops["verify"] += 1
                    last_verify = time.monotonic()
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
        gc.collect()
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass
        rss_quiescent = _rss_kb()
    finally:
        elapsed = max(time.monotonic() - started, 0.001)
        leg.finish()

    append_rps = leg.appends / elapsed
    append_verify_ok = leg.all_verified and leg.segments >= 1
    drift = None
    if rss_start and rss_end:
        drift = round(100.0 * (rss_end - rss_start) / rss_start, 2)
    retention_ok = (
        rss_quiescent is None
        or rss_start is None
        or rss_quiescent <= rss_start * 1.25 + 25_000
    )
    passed = (
        not errors
        and final_verify_ok
        and append_verify_ok
        and append_rps >= APPEND_BUDGET_RPS
        and retention_ok
    )
    return {
        "claim": "S3",
        "duration_s": duration,
        "ops": ops,
        "errors": errors,
        "rss_start_kb": rss_start,
        "rss_end_kb": rss_end,
        "rss_drift_pct": drift,
        "rss_quiescent_kb": rss_quiescent,
        "retention_ok": retention_ok,
        "append_rps": round(append_rps, 1),
        "append_budget_rps": APPEND_BUDGET_RPS,
        "append_segments": leg.segments,
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
