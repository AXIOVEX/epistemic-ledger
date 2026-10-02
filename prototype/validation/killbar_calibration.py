"""Kill-bar calibration battery (KILL-BARS-01).

KILL_BARS were set from single workloads: trigger bars and flag
bars from TRIGGER-STRESS-01, churn from CHURN-01, brier tripped
once in NEWSROOM-01, and max_fanout / n_open_contradictions /
override_rate marked provisional with no calibration data at all.
This battery measures every bar across the program's healthy
workload families and reports observed ranges against the bars:

  stress A   TRIGGER-STRESS-01 config (300 claims / 40 facts)
  stress B   hub-heavier config (600 claims / 25 facts, seed 7)
  newsroom   modeled trials, seeds 0-9 (0-4 published, 5-9 fresh)

Adjustment rule, fixed before running: a bar is adjusted ONLY if
a healthy workload breaches it, and then to observed_max x 1.25
(rounded up sensibly), with the old value and rationale recorded
in KILL-BARS-01 and the code comment. Bars are never tightened
here — tightening needs failure data, not healthy data. A bar no
workload exercises is reported UNMEASURED, never assumed fine.

Writes killbar_calibration_results.json. CPU-only; unbuffered.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stress"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger import Ledger  # noqa: E402
import workload  # noqa: E402
from newsroom import run_trial  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "killbar_calibration_results.json")


def _save(res):
    with open(RESULTS, "w") as f:
        json.dump(res, f, indent=1)


def stress_block(seed, n_claims, n_facts):
    t0 = time.time()
    m = workload.measure_epsilon(0.005, seed=seed,
                                 n_claims=n_claims, n_facts=n_facts)
    L, d, facts, pos = workload.build_ledger(seed, n_claims, n_facts)
    vals = L.check_kill_bars()["values"]
    import shutil
    shutil.rmtree(d)
    return {"recall": m["mean_recall"], "precision": m["mean_precision"],
            "mean_flags": m["mean_flags"], "max_flags": m["max_flags"],
            "max_fanout": vals["max_fanout"],
            "max_material_churn": vals["max_material_churn"],
            "override_rate": vals["override_rate"],
            "n_open_contradictions": vals["n_open_contradictions"],
            "seconds": round(time.time() - t0, 1)}


def main():
    res = {}
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            res = json.load(f)
    if "stressA" not in res:
        res["stressA"] = stress_block(42, 300, 40)
        _save(res)
        print(f"stressA: {res['stressA']}", flush=True)
    if "stressB" not in res:
        res["stressB"] = stress_block(7, 600, 25)
        _save(res)
        print(f"stressB: {res['stressB']}", flush=True)
    res.setdefault("newsroom", {})
    for seed in range(10):
        key = str(seed)
        if key in res["newsroom"]:
            continue
        le, ne, q, lde, nde, stats, accs, meta = run_trial(seed)
        v = meta["kill_values"]
        res["newsroom"][key] = {
            "ledger_err": le, "brier": v["brier"],
            "max_material_churn": v["max_material_churn"],
            "max_fanout": v["max_fanout"],
            "mean_flags": v["mean_flags"], "max_flags": v["max_flags"],
            "override_rate": v["override_rate"],
            "n_open_contradictions": v["n_open_contradictions"]}
        _save(res)
        print(f"newsroom seed {seed}: brier={v['brier']:.3f} "
              f"churn={v['max_material_churn']} "
              f"fanout={v['max_fanout']} "
              f"open={v['n_open_contradictions']}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
