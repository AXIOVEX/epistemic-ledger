"""Agent inference calibration (CALIBRATION-01).

NEWSROOM-01's known defect: the newsroom agents' posteriors are
accurate but overconfident — seed 2 tripped the Brier kill bar
(0.29 > 0.25) at ~83% accuracy, because a learned accuracy of
~0.9 makes every report worth lambda ~ 9 in odds. This is agent
inference, not ledger machinery (fact-claim Brier diagnostic was
0.062): the ledger integrates whatever the agent asserts.

Lever: tempering. bayes_update(..., temper) raises each report's
likelihood ratio to a power < 1 — temperature scaling on the
agent's evidence integration. Both agents in a trial share the
temper, so the ledger-vs-naive comparison stays fair.

Protocol, fixed before any run:
  DEV sweep: tempers {1.0, 0.75, 0.5, 0.35} x seeds 0-4 (the
  published NEWSROOM-01 seeds), modeled extractor, 60 steps.
  Candidate = the LARGEST temper < 1.0 with (a) worst-seed Brier
  <= 0.25 (the kill bar seed 2 breached), (b) mean ledger_err no
  more than 0.005 worse than the temper=1.0 baseline, (c) mean
  Brier strictly better than baseline. No candidate -> no change.
  HELD-OUT: seeds 5-9 (never used in any published run), baseline
  vs candidate only. Adopt the candidate as the agent default iff
  held-out worst-seed Brier <= 0.25 AND mean ledger_err no more
  than 0.01 worse than baseline AND mean Brier improves. Otherwise
  temper stays 1.0 and the negative result is the report.

Checkpointed to calibration_results.json. CPU-only (modeled
extractor); run unbuffered.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsroom import run_trial  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "calibration_results.json")
TEMPERS = (1.0, 0.75, 0.5, 0.35)
DEV_SEEDS = (0, 1, 2, 3, 4)
HELDOUT_SEEDS = (5, 6, 7, 8, 9)


def _load():
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            return json.load(f)
    return {}


def _save(res):
    with open(RESULTS, "w") as f:
        json.dump(res, f, indent=1)


def run(res, phase, temper, seeds):
    res.setdefault(phase, {}).setdefault(str(temper), {})
    for seed in seeds:
        key = str(seed)
        if key in res[phase][str(temper)]:
            continue
        t0 = time.time()
        le, ne, q, lde, nde, stats, accs, meta = run_trial(
            seed, temper=temper)
        res[phase][str(temper)][key] = {
            "ledger_err": le, "naive_err": ne,
            "ledger_derived_err": lde, "naive_derived_err": nde,
            "brier": meta["brier"], "kill_ok": meta["kill_ok"],
            "breached": meta["breached"],
            "seconds": round(time.time() - t0, 1)}
        _save(res)
        print(f"{phase} temper={temper} seed={seed}: ledger={le:.3f} "
              f"brier={meta['brier']:.3f} kill_ok={meta['kill_ok']} "
              f"({res[phase][str(temper)][key]['seconds']}s)",
              flush=True)


def summarize(rows):
    rows = list(rows.values())
    return {"mean_ledger_err": sum(r["ledger_err"] for r in rows)
            / len(rows),
            "mean_brier": sum(r["brier"] for r in rows) / len(rows),
            "worst_brier": max(r["brier"] for r in rows)}


def main():
    res = _load()
    for t in TEMPERS:
        run(res, "dev", t, DEV_SEEDS)
    base = summarize(res["dev"]["1.0"])
    print(f"dev baseline (temper 1.0): {base}", flush=True)
    candidate = None
    for t in sorted((t for t in TEMPERS if t < 1.0), reverse=True):
        s = summarize(res["dev"][str(t)])
        print(f"dev temper {t}: {s}", flush=True)
        if (s["worst_brier"] <= 0.25
                and s["mean_ledger_err"] <= base["mean_ledger_err"]
                + 0.005
                and s["mean_brier"] < base["mean_brier"]):
            candidate = t
            break
    res["candidate"] = candidate
    _save(res)
    print(f"candidate: {candidate}", flush=True)
    if candidate is None:
        res["verdict"] = "no candidate met the dev rule; temper stays 1.0"
        _save(res)
        print("DONE", flush=True)
        return
    run(res, "heldout", 1.0, HELDOUT_SEEDS)
    run(res, "heldout", candidate, HELDOUT_SEEDS)
    hb = summarize(res["heldout"]["1.0"])
    hc = summarize(res["heldout"][str(candidate)])
    print(f"heldout baseline: {hb}", flush=True)
    print(f"heldout candidate {candidate}: {hc}", flush=True)
    adopt = (hc["worst_brier"] <= 0.25
             and hc["mean_ledger_err"] <= hb["mean_ledger_err"] + 0.01
             and hc["mean_brier"] < hb["mean_brier"])
    res["verdict"] = (f"ADOPT temper={candidate}" if adopt else
                      "held-out did not confirm; temper stays 1.0")
    _save(res)
    print(f"verdict: {res['verdict']}", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
