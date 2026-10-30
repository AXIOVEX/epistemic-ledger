"""Kill-point sweep for crash consistency (DESIGN-16, claim S1).

Each trial spawns an append worker (tools.stress.worker_append) against
a fresh store, waits a random moment, and SIGKILLs it — a kill between
any two instructions, not at chosen points. The store is then examined
and the trial is classified:

- ``clean`` — the store opens, verifies, and holds exactly a prefix of
  the attempted appends that includes every acknowledged append (at
  most the one in-flight append may sit beyond the ack frontier).
- ``loud_recoverable`` — the store refuses or reports damage, but the
  damage is confined to the tail and the documented recovery
  (truncate the torn tail / rebuild the projection) restores exactly
  the prefix above. A finding, never a silent pass.
- ``silent_wrong`` — the store verifies but its contents break the
  prefix property: an acknowledged record missing, a gap, a duplicate,
  disorder. The one unforgivable outcome.
- ``error`` — the trial machinery itself failed.

Usage:
    python -m tools.stress.killpoint --engine both --trials 25 \
        --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_HEX = "07" * 32
ACTOR = "stress-writer"


def read_acks(path: Path) -> tuple[list[int], int | None]:
    """Ack file -> (acknowledged indices, partial trailing index|None).

    Only newline-terminated lines count as acknowledged; a trailing
    fragment is the ack the kill interrupted.
    """
    if not path.exists():
        return [], None
    raw = path.read_bytes()
    if not raw:
        return [], None
    parts = raw.split(b"\n")
    acked = [int(p) for p in parts[:-1] if p.strip()]
    partial = None
    if parts[-1].strip():
        try:
            partial = int(parts[-1])
        except ValueError:
            partial = None
    return acked, partial


def _prefix_verdict(recovered: list[int], acked: list[int], partial: int | None) -> str:
    if recovered != list(range(len(recovered))):
        return "silent_wrong"  # gap, duplicate, or disorder
    if not set(acked) <= set(recovered):
        return "silent_wrong"  # an acknowledged record is gone
    slack = len(recovered) - len(acked)
    allowed = 2 if (partial is not None and partial == len(acked)) else 1
    if slack > allowed:
        return "silent_wrong"  # records beyond the in-flight append
    return "clean"


def check_rust(store_dir: str, acked: list[int], partial: int | None) -> dict:
    from epistemic_ledger._core import RustStore
    from epistemic_ledger.ed25519 import publickey

    pub = publickey(bytes.fromhex(SEED_HEX)).hex()
    store = RustStore.open(store_dir)  # performs torn-tail repair
    report = json.loads(store.open_report_json())
    verified = store.verify(json.dumps({ACTOR: pub}))
    recovered: list[int] | None = None
    if hasattr(store, "read_records_json"):
        records = json.loads(store.read_records_json())
        try:
            recovered = [int(r["payload"]["i"]) for r in records]
        except (KeyError, TypeError, ValueError):
            recovered = None
    if recovered is None:
        recovered = list(range(verified))
        mode = "count-only"
    else:
        mode = "records"
        if len(recovered) != verified:
            return {"outcome": "silent_wrong", "detail": "verify count != record count"}
    verdict = _prefix_verdict(recovered, acked, partial)
    return {
        "outcome": verdict,
        "detail": f"mode={mode} torn_bytes={report.get('torn_bytes')}",
        "recovered": len(recovered),
    }


def _python_log_tail(path: Path) -> tuple[int, bool]:
    """(complete-line count, tail_is_torn) for the Python engine's log."""
    raw = path.read_bytes()
    if not raw:
        return 0, False
    lines = raw.split(b"\n")
    complete = lines[:-1]  # last element is "" (clean end) or the torn line
    torn = not raw.endswith(b"\n")
    for line in complete:
        json.loads(line)  # raises if a complete line is corrupt
    return len(complete), torn


def check_python(store_dir: str, acked: list[int], partial: int | None) -> dict:
    from epistemic_ledger import Ledger

    store = Path(store_dir)
    log = store / "events.jsonl"

    def claims_of(led: Ledger) -> list[int]:
        idx = []
        for claim in led.list_claims():  # list_claims returns plain dicts
            idx.append(int(claim["statement"].rsplit("-", 1)[1]))
        return sorted(idx)

    loud = None
    try:
        led = Ledger(store_dir)
        findings = led.verify_store()
        if findings:
            loud = f"verify_store findings: {len(findings)}"
        else:
            recovered = claims_of(led)
            led.close()
            return {
                "outcome": _prefix_verdict(recovered, acked, partial),
                "detail": "verify_store clean",
                "recovered": len(recovered),
            }
        led.close()
    except Exception as exc:  # open or verify refused — loud, maybe recoverable
        loud = f"{type(exc).__name__}: {exc}"

    # Recovery path: damage must be confined to the log's tail. Truncate
    # a torn final line, rebuild the projection, and re-check.
    try:
        complete, torn = _python_log_tail(log)
        if torn:
            raw = log.read_bytes()
            log.write_bytes(raw[: raw.rfind(b"\n") + 1])
        Ledger.rebuild_projection(store_dir)
        led = Ledger(store_dir)
        findings = led.verify_store()
        if findings:
            led.close()
            return {"outcome": "silent_wrong", "detail": f"after recovery: {findings[:2]}"}
        recovered = claims_of(led)
        led.close()
        verdict = _prefix_verdict(recovered, acked, partial)
        if verdict != "clean":
            return {"outcome": "silent_wrong", "detail": f"after recovery: {verdict}"}
        return {
            "outcome": "loud_recoverable",
            "detail": f"{loud}; tail lines kept={complete} torn={torn}",
            "recovered": len(recovered),
        }
    except Exception as exc:
        return {"outcome": "error", "detail": f"recovery failed: {type(exc).__name__}: {exc}"}


def run_trial(engine: str, rng: random.Random, count: int) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix=f"killpoint-{engine}-"))
    store_dir = tmp / "store"
    ack_path = tmp / "ack.txt"
    ready_path = tmp / "ready.txt"
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "tools.stress.worker_append",
            "--store", str(store_dir), "--engine", engine,
            "--count", str(count), "--ack", str(ack_path),
            "--ready", str(ready_path), "--delay-ms", "1.0",
        ],
        cwd=REPO_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 60
        while not ready_path.exists():
            if proc.poll() is not None:
                return {"engine": engine, "outcome": "error", "detail": "worker died before ready"}
            if time.time() > deadline:
                return {"engine": engine, "outcome": "error", "detail": "worker never ready"}
            time.sleep(0.01)
        time.sleep(rng.uniform(0.02, 1.2))
        proc.send_signal(signal.SIGKILL)
        proc.wait(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
    acked, partial = read_acks(ack_path)
    checker = check_rust if engine == "rust" else check_python
    try:
        result = checker(str(store_dir), acked, partial)
    except Exception as exc:
        result = {"outcome": "error", "detail": f"checker: {type(exc).__name__}: {exc}"}
    result.update({"engine": engine, "acked": len(acked)})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["rust", "python", "both"], default="both")
    parser.add_argument("--trials", type=int, default=25)
    parser.add_argument("--count", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    engines = ["rust", "python"] if args.engine == "both" else [args.engine]
    results = []
    for engine in engines:
        for _ in range(args.trials):
            results.append(run_trial(engine, rng, args.count))
    summary: dict[str, dict[str, int]] = {}
    for r in results:
        summary.setdefault(r["engine"], {}).setdefault(r["outcome"], 0)
        summary[r["engine"]][r["outcome"]] += 1
    report = {"claim": "S1", "trials": results, "summary": summary}
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(json.dumps(summary, indent=2))
    bad = any(
        r["outcome"] in ("silent_wrong", "error") for r in results
    )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
