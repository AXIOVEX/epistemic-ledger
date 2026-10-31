"""Resource floors (DESIGN-16, claim S5).

Two legs, one report:

- **Disk.** A genuine ENOSPC, not a simulated one: a small
  loopback filesystem (a 96 MB image, ext4, mounted with sudo —
  the CI runners grant it) is filled by chained-store appends.
  The floor: the append that hits the full disk fails LOUDLY
  (an error, never a silent short write), and the store then
  reopens and verifies at exactly the count of appends that
  succeeded — DESIGN-14's semantics under a real full disk.
  Where the loopback setup is unavailable, the leg reports
  ``not_run`` with the reason; it never fakes a pass.
- **Memory.** Full verification of the 100k-record reference
  store under a 256 MB ceiling. Where systemd-run is available
  the ceiling is enforced by a cgroup scope; elsewhere the
  child's peak resident size is measured and compared, and the
  report says which mode produced the verdict (``enforced``).

Usage:
    python -m tools.stress.floors --out report.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SEED_HEX = "07" * 32
ACTOR = "stress-writer"
PAYLOAD = json.dumps({"data": "x" * 4096})
REPO_ROOT = Path(__file__).resolve().parents[2]


def _sudo_ok() -> bool:
    if shutil.which("sudo") is None:
        return False
    r = subprocess.run(["sudo", "-n", "true"], capture_output=True)
    return r.returncode == 0


def run_disk_floor(image_mb: int = 96) -> dict:
    leg: dict = {"leg": "disk", "status": "not_run", "detail": None}
    if sys.platform != "linux" or not _sudo_ok():
        leg["detail"] = "needs Linux with passwordless sudo for the loopback mount"
        return leg
    tmp = Path(tempfile.mkdtemp(prefix="floor-disk-"))
    image = tmp / "disk.img"
    mnt = tmp / "mnt"
    mnt.mkdir()
    mounted = False
    try:
        for cmd in (
            ["fallocate", "-l", f"{image_mb}M", str(image)],
            ["mkfs.ext4", "-q", str(image)],
            ["sudo", "mount", "-o", "loop", str(image), str(mnt)],
            ["sudo", "mkdir", str(mnt / "store")],
            ["sudo", "chown", f"{os.getuid()}:{os.getgid()}", str(mnt / "store")],
        ):
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                leg["detail"] = (
                    f"setup failed at {' '.join(cmd[:2])}: {r.stderr.strip()[:160]}"
                )
                return leg
            if cmd[1] == "mount":
                mounted = True
        from epistemic_ledger._core import RustStore
        from epistemic_ledger.ed25519 import publickey

        pub = publickey(bytes.fromhex(SEED_HEX)).hex()
        store_dir = str(mnt / "store")
        store = RustStore.open(store_dir)
        succeeded = 0
        loud = False
        try:
            while True:
                store.append(
                    "2026-01-01T00:00:00Z", ACTOR, "stress_record", PAYLOAD, SEED_HEX
                )
                succeeded += 1
        except Exception:
            loud = True  # the append failed loudly, as required
        del store
        reopened = RustStore.open(store_dir)
        verified = reopened.verify(json.dumps({ACTOR: pub}), 1)
        del reopened
        leg.update(
            {
                "successful_appends": succeeded,
                "loud_failure": loud,
                "verified_after": verified,
                "status": "pass" if (loud and verified == succeeded) else "fail",
            }
        )
        return leg
    finally:
        if mounted:
            subprocess.run(["sudo", "umount", str(mnt)], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def _verify_child(store_dir: str) -> int:
    """Child mode: verify the store, print {verified, peak_rss_kb}."""
    import resource

    from epistemic_ledger._core import RustStore
    from epistemic_ledger.ed25519 import publickey

    pub = publickey(bytes.fromhex(SEED_HEX)).hex()
    store = RustStore.open(store_dir)
    verified = store.verify(json.dumps({ACTOR: pub}), 1)
    peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({"verified": verified, "peak_rss_kb": peak_kb}))
    return 0


def run_memory_floor(records: int = 100_000, ceiling_mb: int = 256) -> dict:
    from epistemic_ledger._core import RustStore

    leg: dict = {"leg": "memory", "status": "fail", "detail": None}
    tmp = Path(tempfile.mkdtemp(prefix="floor-mem-"))
    try:
        store_dir = str(tmp / "store")
        store = RustStore.open(store_dir)
        for i in range(records):
            store.append(
                "2026-01-01T00:00:00Z",
                ACTOR,
                "stress_record",
                json.dumps({"i": i}),
                SEED_HEX,
            )
        del store
        child = [
            sys.executable,
            "-m",
            "tools.stress.floors",
            "--verify-child",
            store_dir,
        ]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        enforced = False
        cmd = child
        if sys.platform == "linux" and _sudo_ok() and shutil.which("systemd-run"):
            cmd = [
                "sudo",
                "systemd-run",
                "--scope",
                "--quiet",
                "-p",
                f"MemoryMax={ceiling_mb}M",
                "-p",
                "MemorySwapMax=0",
            ] + child
            enforced = True
        r = subprocess.run(cmd, capture_output=True, text=True, env=env)
        leg["enforced"] = enforced
        if r.returncode != 0:
            leg["detail"] = f"verify child failed: {r.stderr.strip()[-200:]}"
            return leg
        out = json.loads(r.stdout.strip().splitlines()[-1])
        leg["verified"] = out["verified"]
        leg["peak_rss_kb"] = out["peak_rss_kb"]
        ok = out["verified"] == records
        if not enforced:
            ok = ok and out["peak_rss_kb"] <= ceiling_mb * 1024
        leg["status"] = "pass" if ok else "fail"
        return leg
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_floors(
    records: int = 100_000, ceiling_mb: int = 256, image_mb: int = 96
) -> dict:
    disk = run_disk_floor(image_mb)
    memory = run_memory_floor(records, ceiling_mb)
    return {
        "claim": "S5",
        "legs": {"disk": disk, "memory": memory},
        "passed": disk["status"] == "pass" and memory["status"] == "pass",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=100_000)
    parser.add_argument("--ceiling-mb", type=int, default=256)
    parser.add_argument("--image-mb", type=int, default=96)
    parser.add_argument("--out", default=None)
    parser.add_argument("--verify-child", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.verify_child:
        return _verify_child(args.verify_child)
    report = run_floors(args.records, args.ceiling_mb, args.image_mb)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
