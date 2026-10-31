"""Soak legs (DESIGN-16, claim S3).

S3 is measured by two legs that run as SEPARATE invocations,
each on its own runner at both tiers:

- the mixed leg (`--leg mixed`) — one Python Ledger under
  interleaved asserts, score revisions, supports, impact
  analyses, LQL queries, and periodic full verifications (on a
  time cadence: a cycle-count cadence makes each verification's
  cost grow with the store it is checking). It passes with zero
  errors, a clean full verification at the end, and memory
  retention inside its bound (below).
- the append leg (`--leg append`) — the chained store under a
  full-rate append worker. It gates on endurance and
  integrity: the full duration sustained, every rotated
  segment verified, the sustained rate reported as measured.
  The append store ROTATES every 30 minutes:
  the worker is stopped, its segment verified, and a fresh
  store started. Rotation is what the first nightly taught:
  an unbounded 2-hour append leg heads toward ~18M records
  with a full verification of that store still owed at the
  end, and the platform cancelled the step before the report
  was written. Segments bound every verification, and the leg
  keeps its headroom.

Why separate runners, and why the append leg no longer
gates on the rate budget (owner's decision, 2026-10-31):
across four soak runs the append leg measured 1,807 /
1,972 / 1,785 / 1,686 appends/s against the 2,000 budget —
co-located, solo, and on its own runner alike. The gap
could not be attributed to the store from the available
evidence: the soak worker's workload is stricter than the
bench's (a second, fsynced acknowledgement write per
record, which the budget workload does not carry), and
sustained multi-gigabyte writes on hosted-runner storage
throttle in ways a 100k-append bench burst never meets.
The DESIGN-13 budget therefore stays gated where its
workload is measured cleanly — the per-PR bench in the
Battery job, green on this code — and the soak's append
leg gates on what a soak can honestly prove: hours of
sustained appends with every segment verified. Its rate
is still measured and reported every run, so a genuine
regression would show in the record. The legs also run on
separate runners (the co-located shape let the mixed leg's
growing per-cycle cost starve the append worker sharing
its CPUs). All of this is recorded in DESIGN-16.

Memory retention is measured as LIVE TRACED BYTES
(tracemalloc): tracing starts after warm-up, and the leg
passes if the bytes still live after the final verification
— with the ledger closed and dropped, garbage collected —
are within 25% plus 25 MB of the post-warm-up live level.
Two earlier instruments measured the allocator instead of
the program: end-of-run resident size is a high-water mark
under O(store) transients (~26,000% "growth" with ~1 MB
live), and post-close resident size still reads fragmented
arenas (225 MB resident against the same ~1 MB live at
probe scale). Resident figures are still reported, as
measured; the gate is on live bytes. Tracing slows the
mixed leg's operations; it has no rate budget (rates are
reported as measured), and the append leg runs untraced in
its own process on its own runner.

Usage:
    python -m tools.stress.soak --leg mixed \
        --duration-seconds 7200 --out soak.json
    python -m tools.stress.soak --leg append \
        --duration-seconds 7200 --out soak-append.json
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
import tracemalloc
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APPEND_BUDGET_RPS = 2000.0
WARMUP_CLAIMS = 300
ROTATE_SECONDS = 1800.0
VERIFY_EVERY_SECONDS = 600.0
RETENTION_SLACK_BYTES = 25_000_000


def _rss_kb() -> int | None:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


def _trim_allocator() -> None:
    gc.collect()
    try:
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


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


def run_append_soak(duration: float) -> dict:
    """The append leg alone: a full-rate chained-store worker
    on this runner, rotated and verified per segment. The
    leg passes on endurance and integrity — every segment
    verified inside the S1 prefix tolerance; the sustained
    rate (appends over the whole window, segment
    verifications included) is reported as measured, and
    the DESIGN-13 rate budget is gated by the per-PR bench
    (see the module docstring's re-scope note)."""
    tmp = Path(tempfile.mkdtemp(prefix="soak-append-"))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    leg = _AppendLeg(tmp, env)
    started = time.monotonic()
    leg.start()
    deadline = started + duration
    while time.monotonic() < deadline:
        leg.maybe_rotate()
        time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
    leg.finish()
    elapsed = max(time.monotonic() - started, 0.001)

    append_rps = leg.appends / elapsed
    append_verify_ok = leg.all_verified and leg.segments >= 1
    return {
        "claim": "S3",
        "leg": "append",
        "duration_s": duration,
        "appends": leg.appends,
        "append_rps": round(append_rps, 1),
        "append_budget_rps": APPEND_BUDGET_RPS,
        "append_segments": leg.segments,
        "append_verify_ok": append_verify_ok,
        "passed": append_verify_ok,
    }


def run_soak(duration: float, seed: int | None = None) -> dict:
    """The mixed leg: one Python Ledger under interleaved
    operations for the duration (see the module docstring)."""
    from epistemic_ledger import Ledger

    rng = random.Random(seed)
    tmp = Path(tempfile.mkdtemp(prefix="soak-"))

    errors: list[dict] = []
    ops = {"assert": 0, "score": 0, "support": 0, "impact": 0, "query": 0, "verify": 0}
    final_verify_ok = False
    rss_start = None
    rss_end = None
    rss_quiescent = None
    live_start = None
    live_end = None
    started = time.monotonic()
    led = Ledger(str(tmp / "mixed-store"))
    ids: list[str] = []
    for i in range(WARMUP_CLAIMS):
        cid = led.assert_claim(f"soak-warm-{i}", 0.5)
        if ids:
            led.add_support(ids[-1], cid, "evidential", 0.8, 0.3)
        ids.append(cid)
    rss_start = _rss_kb()
    tracemalloc.start()
    live_start = tracemalloc.get_traced_memory()[0]
    deadline = started + duration
    last_verify = time.monotonic()
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
    del led
    _trim_allocator()
    rss_quiescent = _rss_kb()
    live_end = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()

    drift = None
    if rss_start and rss_end:
        drift = round(100.0 * (rss_end - rss_start) / rss_start, 2)
    retention_ok = (
        live_start is None
        or live_end is None
        or live_end <= live_start + live_start // 4 + RETENTION_SLACK_BYTES
    )
    passed = not errors and final_verify_ok and retention_ok
    return {
        "claim": "S3",
        "leg": "mixed",
        "duration_s": duration,
        "ops": ops,
        "errors": errors,
        "rss_start_kb": rss_start,
        "rss_end_kb": rss_end,
        "rss_drift_pct": drift,
        "rss_quiescent_kb": rss_quiescent,
        "live_start_kb": None if live_start is None else live_start // 1024,
        "live_end_kb": None if live_end is None else live_end // 1024,
        "retention_ok": retention_ok,
        "final_verify_ok": final_verify_ok,
        "passed": passed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--leg", choices=["mixed", "append"], default="mixed")
    parser.add_argument("--duration-seconds", type=float, default=7200.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if args.leg == "append":
        report = run_append_soak(args.duration_seconds)
    else:
        report = run_soak(args.duration_seconds, args.seed)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
