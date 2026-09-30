"""End-to-end demo of the living epistemic ledger v0.1.

Scenario: a bridge-design safety claim, a load-test evidence claim, a
ship-date claim depending on safety, then a supplier-delay fact that forces
a revisit. Run:  python demo.py
"""

import shutil
import tempfile

from ledger import Ledger


def main():
    d = tempfile.mkdtemp(prefix="ledger-demo-")
    L = Ledger(d)

    # --- day 1: the initial web of belief ---------------------------------
    safe = L.assert_claim("bridge design is safe", 0.60)
    ships = L.assert_claim("project ships on time", 0.55)
    # ships-on-time rests on design safety (deductive-ish link)
    L.add_support(ships, safe, "deductive", p_given=0.90, p_given_not=0.20)

    print(f"day 1: safe={L._live_claim(safe)['score']:.3f} "
          f"ships={L._live_claim(ships)['score']:.3f}")

    # --- day 2: load test passes; safety is revisited ----------------------
    r = L.ingest_evidence("load test passed", 0.90)
    fact = r["fact_id"]
    L.add_support(safe, fact, "evidential", p_given=0.95, p_given_not=0.30)
    r = L._revisit(fact, {fact: 0.90})
    print(f"day 2: load test passed -> safe={L._live_claim(safe)['score']:.3f} "
          f"(+{r['updates'][0]['delta']:+.3f}), "
          f"ships={L._live_claim(ships)['score']:.3f} "
          f"(+{r['updates'][1]['delta']:+.3f})")

    # --- day 3: supplier delay arrives; the ledger revisits -----------------
    r = L.ingest_evidence("steel supplier delayed 6 weeks", 0.85)
    delay = r["fact_id"]
    L.add_support(ships, delay, "evidential", p_given=0.15, p_given_not=0.70)
    r = L._revisit(delay, {delay: 0.85})
    print(f"day 3: supplier delay -> ships={L._live_claim(ships)['score']:.3f} "
          f"({r['updates'][0]['delta']:+.3f}); "
          f"flags raised: {len(r['flags'])}")

    # --- queries ------------------------------------------------------------
    print("\nWHY(ships):")
    for w in L.why(ships):
        print(f"  <- {w['statement']!r} score={w['score']:.3f} kind={w['kind']}")
    print(f"\nDEPENDS_ON(delay): {len(L.depends_on(delay))} claim(s) in closure")

    # --- the ledger scores itself -------------------------------------------
    L.record_outcome(safe, True)   # design held up
    L.record_outcome(ships, False)  # shipped late
    m = L.kill_metrics()
    print(f"\nkill metrics: brier={m['brier']:.3f} "
          f"fanout_max={m['fanout']['max']} "
          f"override_rate={m['override_rate']} "
          f"revisits={len(m['trigger_log'])}")
    shutil.rmtree(d)


if __name__ == "__main__":
    main()
