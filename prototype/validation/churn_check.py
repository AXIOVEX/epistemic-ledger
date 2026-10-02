"""Calibration for material churn (CHURN-01, Design Memo 09).

Workloads:
  HEALTHY     — newsroom, 5 seeds x 60 steps (adversarial sources,
                honest tracking). Raw churn reaches 9 here.
  JITTER-A     — a claim hand-set +-0.02 around 0.5 (direct).
  JITTER-B     — a noisy-and combo whose parents wobble +-0.04 via
                the agent's own _set pattern (propagated residue).
  OSCILLATION  — a claim hand-set 0.3 <-> 0.7: repeated MATERIAL
                position flips. The pathology the bar exists for
                (broken integrator / absurd per-report weight).
  BIG-SWING    — 0.15 <-> 0.85 alternation: same pathology, larger.

Expected (measured, CHURN-01): HEALTHY per-seed max material churn
2-7; JITTER 0 (absorbed — sub-materiality movement changes no
decision); OSCILLATION and BIG-SWING at 9. Bar set at 8: above
healthy, below pathology.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger import Ledger  # noqa: E402
from head_to_head import build_agent  # noqa: E402


def healthy():
    print("HEALTHY (newsroom 60 steps):")
    worst_raw = worst_mat = 0
    for seed in range(5):
        agent = build_agent(seed=seed, steps=60)
        d = agent.L.kill_metrics()["churn_detail"]
        raw = max(v["raw"] for v in d.values())
        mat = max(v["material_churn"] for v in d.values())
        worst_raw = max(worst_raw, raw)
        worst_mat = max(worst_mat, mat)
        print(f"  seed {seed}: max raw={raw}  max material_churn={mat}")
        agent.close()
    print(f"  -> healthy worst: raw={worst_raw} material={worst_mat}")
    return worst_mat


def _alternating(lo, hi, n=20):
    d = tempfile.mkdtemp(prefix="churn-w-")
    L = Ledger(d)
    c = L.assert_claim("workload claim", 0.5)
    for i in range(n):
        L.manual_score(c, hi if i % 2 == 0 else lo)
    det = L.kill_metrics()["churn_detail"][c]
    shutil.rmtree(d)
    return det


def jitter_propagated():
    d = tempfile.mkdtemp(prefix="jitter-b-")
    L = Ledger(d)
    p1 = L.assert_claim("parent one", 0.5)
    p2 = L.assert_claim("parent two", 0.5)
    c = L.assert_claim("combo claim", 0.5)
    L.add_support(c, p1, "evidential")
    L.add_support(c, p2, "evidential")
    L.set_combo(c, "noisy-and")
    for i in range(20):
        target = 0.54 if i % 2 == 0 else 0.46
        L._set_score(p1, target, None, actor="agent")
        L._revisit(p1, {p1: target}, actor="agent")
    det = L.kill_metrics()["churn_detail"][c]
    print(f"JITTER-B (propagated): raw={det['raw']} "
          f"material_moves={det['material_moves']} "
          f"material_churn={det['material_churn']}")
    shutil.rmtree(d)
    return det["material_churn"]


if __name__ == "__main__":
    h = healthy()
    ja = _alternating(0.49, 0.51)
    print(f"JITTER-A (direct +-0.02): raw={ja['raw']} "
          f"material_churn={ja['material_churn']}")
    jb = jitter_propagated()
    osc = _alternating(0.3, 0.7)
    print(f"OSCILLATION (0.3<->0.7): raw={osc['raw']} "
          f"material_churn={osc['material_churn']}")
    big = _alternating(0.15, 0.85)
    print(f"BIG-SWING (0.15<->0.85): raw={big['raw']} "
          f"material_churn={big['material_churn']}")
    print(f"\nseparation: healthy max {h} | jitter {ja['material_churn']}/"
          f"{jb} (absorbed) | pathology min "
          f"{min(osc['material_churn'], big['material_churn'])}")
    print("bar must sit above healthy and below pathology.")
