"""Scale smoke (DESIGN-12): the prototype's measured envelope.

Builds a 10,000-claim DAG ledger (stress-workload shape) plus 200
hub facts, then times the operations a deployment cares about:
build/ingest, one hub-fact revision (worst-case revisit fan-out),
a believed_at snapshot, and a full verify_store pass. Prints the
numbers; they are quoted in DESIGN-12 as the v0.11 envelope on
this machine class (2-CPU VM). Not a benchmark — a smoke test that
the store behaves sanely an order of magnitude past every
validation workload (which peak at 600 claims).
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stress"))
import workload  # noqa: E402
from ledger import _now  # noqa: E402


def main():
    t0 = time.time()
    L, d, facts, pos = workload.build_ledger(99, 10_000, 200)
    t_build = time.time() - t0
    n_events = len(L._events())

    hub, cred = facts[0]
    t0 = time.time()
    L.ingest_evidence(hub, 0.05, actor="smoke")
    t_revisit = time.time() - t0

    t0 = time.time()
    snap = L.believed_at(_now())
    t_snap = time.time() - t0

    t0 = time.time()
    rep = L.verify_store()
    t_verify = time.time() - t0

    print(f"claims=10000 facts=200 events={n_events}")
    print(f"build:        {t_build:.1f}s")
    print(f"hub revisit:  {t_revisit:.2f}s (one fact, full fan-out)")
    print(f"believed_at:  {t_snap:.2f}s ({len(snap)} live claims)")
    print(f"verify_store: {t_verify:.1f}s ok={rep['ok']} "
          f"checked={rep['claims_checked']}")
    import shutil
    shutil.rmtree(d)


if __name__ == "__main__":
    main()
