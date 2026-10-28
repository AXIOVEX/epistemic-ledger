"""Command-line interface for the living epistemic ledger.

Commands:
    epistemic-ledger demo                     run the end-to-end scenario
    epistemic-ledger verify <ledger-dir>      integrity-check a ledger store
    epistemic-ledger kill-metrics <ledger-dir>
                                              print the five kill metrics
                                              as JSON

Exit codes: 0 on success, 1 when a check reports problems, 2 on usage
or open errors.
"""

import argparse
import json
import shutil
import sys
import tempfile

from . import __version__
from .ledger import Ledger


def run_demo():
    """The bridge scenario from the framing work, end to end."""
    d = tempfile.mkdtemp(prefix="ledger-demo-")
    try:
        L = Ledger(d)

        safe = L.assert_claim("bridge design is safe", 0.60)
        ships = L.assert_claim("project ships on time", 0.55)
        L.add_support(ships, safe, "deductive", p_given=0.90, p_given_not=0.20)
        print(f"day 1: safe={L.get_score(safe):.3f} ships={L.get_score(ships):.3f}")

        r = L.ingest_evidence("load test passed", 0.90)
        fact = r["fact_id"]
        before = L.get_score(safe)
        L.add_support(safe, fact, "evidential", p_given=0.95, p_given_not=0.30)
        L._revisit(fact, {fact: 0.90})
        print(
            f"day 2: load test passed -> safe={L.get_score(safe):.3f} "
            f"({L.get_score(safe) - before:+.3f}), "
            f"ships={L.get_score(ships):.3f}"
        )

        r = L.ingest_evidence("steel supplier delayed 6 weeks", 0.85)
        delay = r["fact_id"]
        before = L.get_score(ships)
        L.add_support(ships, delay, "evidential", p_given=0.15, p_given_not=0.70)
        r = L._revisit(delay, {delay: 0.85})
        print(
            f"day 3: supplier delay -> ships={L.get_score(ships):.3f} "
            f"({L.get_score(ships) - before:+.3f}); "
            f"flags raised: {len(r['flags'])}"
        )

        print("\nWHY(ships):")
        for w in L.why(ships):
            print(f"  <- {w['statement']!r} score={w['score']:.3f} kind={w['kind']}")
        print(f"\nDEPENDS_ON(delay): {len(L.depends_on(delay))} claim(s) in closure")

        L.record_outcome(safe, True)
        L.record_outcome(ships, False)
        m = L.kill_metrics()
        print(
            f"\nkill metrics: brier={m['brier']:.3f} "
            f"fanout_max={m['fanout']['max']} "
            f"override_rate={m['override_rate']} "
            f"revisits={len(m['trigger_log'])}"
        )
        L.close()
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="epistemic-ledger",
        description="Living epistemic ledger: append-only conclusions "
        "with fluid certainty scores.",
    )
    parser.add_argument(
        "--version", action="version", version=f"epistemic-ledger {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="run the end-to-end demo scenario")
    p_verify = sub.add_parser("verify", help="integrity-check a ledger store")
    p_verify.add_argument("ledger_dir")
    p_km = sub.add_parser("kill-metrics", help="print a ledger's kill metrics as JSON")
    p_km.add_argument("ledger_dir")
    p_mig = sub.add_parser(
        "migrate", help="migrate a 0.12 store into the chained Rust format"
    )
    p_mig.add_argument("src_dir")
    p_mig.add_argument("dst_dir")
    args = parser.parse_args(argv)

    if args.command == "demo":
        return run_demo()
    if args.command == "migrate":
        from .migrate import migrate_store

        try:
            report = migrate_store(args.src_dir, args.dst_dir)
        except Exception as exc:
            print(f"error: migration failed: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report, indent=2, default=str))
        return 0
    try:
        L = Ledger(args.ledger_dir)
    except Exception as exc:  # an unopenable store is a usage error
        print(f"error: cannot open ledger at {args.ledger_dir}: {exc}", file=sys.stderr)
        return 2
    try:
        if args.command == "verify":
            result = L.verify_store()
            print(json.dumps(result, indent=2, default=str))
            return 0 if result.get("ok") else 1
        if args.command == "kill-metrics":
            print(json.dumps(L.kill_metrics(), indent=2, default=str))
            return 0
    finally:
        L.close()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
