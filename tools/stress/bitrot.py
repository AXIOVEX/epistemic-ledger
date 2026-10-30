"""Bit-rot sweep (DESIGN-16, claim S2).

Builds a chained store, then corrupts single bytes of its log, one at a
time, and requires verification to detect every one. Scope, stated
plainly: the sweep covers the Rust chained store, whose per-line CRC,
hash chain, and signatures are the detection machinery S2 claims. The
legacy Python log's integrity story is verify_store's log/projection
agreement, not per-byte detection, and it is not claimed here.

Interior vs tail: a flip inside records 0..N-2 must be HARD-detected —
open refuses, or verification fails. A flip in the final record's line
is the tail class: the store's crash contract (DESIGN-13) treats tail
damage as a possibly-torn write, so the acceptable outcomes are hard
detection, or the documented repair — the tail truncated and reported
in the open report, exactly that one record gone, the remaining prefix
verifying cleanly. Anything else fails the sweep: a corrupted store
accepted as whole, or a quiet loss of more than the tail record.

Usage:
    python -m tools.stress.bitrot --flips 500 --out report.json
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
from pathlib import Path

SEED_HEX = "07" * 32
ACTOR = "stress-writer"


def build_template(store_dir: Path, records: int) -> None:
    from epistemic_ledger._core import RustStore

    store = RustStore.open(str(store_dir))
    for i in range(records):
        store.append(
            "2026-01-01T00:00:00Z",
            ACTOR,
            "stress_record",
            json.dumps({"i": i, "data": "x" * 64}),
            SEED_HEX,
        )


def _line_spans(raw: bytes) -> list[tuple[int, int]]:
    """(start, content_end) per line; content_end excludes the newline."""
    spans = []
    pos = 0
    for line in raw.split(b"\n")[:-1]:
        spans.append((pos, pos + len(line)))
        pos += len(line) + 1
    return spans


def _probe(store_dir: Path, pub: str, want_records: int) -> str:
    """Classify one corrupted copy.

    Returns "detected", "tail_repair", or "missed" (any silent loss or
    silent acceptance — the failure class).
    """
    from epistemic_ledger._core import RustStore

    try:
        store = RustStore.open(str(store_dir))
    except Exception:
        return "detected"  # open itself refused the corrupted log
    report = json.loads(store.open_report_json())
    torn = report.get("torn_bytes", 0)
    try:
        verified = store.verify(json.dumps({ACTOR: pub}))
    except Exception:
        return "detected"
    if verified == want_records and torn == 0:
        return "missed"  # corrupted store accepted as whole
    if verified == want_records - 1 and torn > 0:
        return "tail_repair"  # exactly the tail record, reported
    if verified == want_records:
        return "missed"  # inconsistent: full count but bytes were torn
    return "missed"  # quiet loss of more than the tail record


def run_sweep(flips: int, records: int, seed: int | None) -> dict:
    from epistemic_ledger.ed25519 import publickey

    pub = publickey(bytes.fromhex(SEED_HEX)).hex()
    rng = random.Random(seed)
    tmp = Path(tempfile.mkdtemp(prefix="bitrot-"))
    template = tmp / "template"
    template.mkdir()
    build_template(template, records)
    raw = (template / "events.log").read_bytes()
    spans = _line_spans(raw)
    assert len(spans) == records, f"template has {len(spans)} lines, want {records}"

    outcomes: dict[str, int] = {"detected": 0, "tail_repair": 0, "missed": 0}
    missed: list[dict] = []
    for n in range(flips):
        # Every tenth flip targets the final record's line (the tail
        # class); the rest target content bytes of lines 0..N-2.
        tail_flip = n % 10 == 9
        line_idx = records - 1 if tail_flip else rng.randrange(0, records - 1)
        start, end = spans[line_idx]
        offset = rng.randrange(start, end)
        work = tmp / "work"
        if work.exists():
            shutil.rmtree(work)
        shutil.copytree(template, work)
        log_path = work / "events.log"
        data = bytearray(log_path.read_bytes())
        data[offset] ^= 0xFF
        log_path.write_bytes(bytes(data))
        outcome = _probe(work, pub, records)
        if outcome == "tail_repair" and not tail_flip:
            outcome = "missed"  # repair class is legitimate only at the tail
        outcomes[outcome] += 1
        if outcome == "missed":
            missed.append({"line": line_idx, "offset": offset, "tail": tail_flip})
    shutil.rmtree(tmp, ignore_errors=True)
    return {
        "claim": "S2",
        "records": records,
        "flips": flips,
        "outcomes": outcomes,
        "missed": missed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flips", type=int, default=500)
    parser.add_argument("--records", type=int, default=200)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    report = run_sweep(args.flips, args.records, args.seed)
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    print(text)
    return 1 if report["outcomes"]["missed"] else 0


if __name__ == "__main__":
    sys.exit(main())
