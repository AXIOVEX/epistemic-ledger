"""Post-freeze downstream validation (the STANCE-02 proof package).

Runs the REALWIRE newsroom payoff protocol - identical to
stance02_downstream (seeds 0-4 x 60 steps, REALWIRE-01 Part 2
scoring, frozen bands vs the 0.4637 reference) - for extractors the
frozen study did not run downstream:

- Q35A: the baseline production prompt served by Qwen3.5-9B (the
  model-fold winner). Model identity is by server provenance: this
  runner executes inside a retargeted copy whose local_chat points
  at the bench server holding the Qwen3.5 GGUF.
- Q35C: the structured protocol (stance02.run_structured, no
  thinking) on that same server.
- F: the STANCE-03 split-call-1 candidate (stance03_census.run_split)
  on whichever local server the copy targets.

Results land in fold_downstream_results.json (this file's own
record; the frozen stance02_downstream_results.json is not touched).
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import newsroom  # noqa: E402
from newsroom import run_trial  # noqa: E402
import realwire_corpus as rc  # noqa: E402
import stance02  # noqa: E402
import stance02_downstream as sd  # noqa: E402
from stance03_census import run_split  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "fold_downstream_results.json")
FACTS = sd.FACTS
FACTS_BLOCK = sd.FACTS_BLOCK


class FoldBaselineAdapter(sd.Adapter):
    def extract(self, sentence, source):
        return self._guarded(lambda: stance02.run_single(
            "A", FACTS_BLOCK, sentence,
            lambda p: stance02.local_chat(p)))


class SplitAdapter(sd.Adapter):
    def extract(self, sentence, source):
        return self._guarded(lambda: run_split(
            FACTS, FACTS_BLOCK, sentence,
            lambda p: stance02.local_chat(p, max_tokens=256)))


FACTORIES = {
    "Q35A": lambda: FoldBaselineAdapter(),
    "Q35C": lambda: sd.StructuredAdapter(False),
    "F": lambda: SplitAdapter(),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=list(FACTORIES))
    ap.add_argument("--seeds", default="0,1,2,3,4")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",")]
    newsroom.FACTS = rc.REALWIRE_FACTS
    res = {}
    if os.path.exists(RESULTS):
        res = json.load(open(RESULTS))
    arm_res = res.setdefault(a.arm, {"seeds": {}})
    for seed in seeds:
        key = str(seed)
        if key in arm_res["seeds"]:
            print(f"[{a.arm}] seed {seed} already done", flush=True)
            continue
        holder = {}

        def factory(rng, _h=holder):
            _h["ext"] = FACTORIES[a.arm]()
            return _h["ext"]

        t0 = time.time()
        le, ne, q, lde, nde, *_ = run_trial(
            seed, steps=60, extractor_factory=factory)
        arm_res["seeds"][key] = {
            "ledger_err": le, "naive_err": ne, "quizzes": q,
            "ledger_derived_err": lde, "naive_derived_err": nde,
            "extract_calls": holder["ext"].calls,
            "abstentions": holder["ext"].abstentions,
            "seconds": round(time.time() - t0, 1)}
        json.dump(res, open(RESULTS, "w"), indent=1)
        print(f"[{a.arm}] seed {seed}: ledger={le:.4f} naive={ne:.4f} "
              f"derived={lde:.4f}/{nde:.4f} calls="
              f"{holder['ext'].calls} abst={holder['ext'].abstentions} "
              f"({arm_res['seeds'][key]['seconds']}s)", flush=True)
    rows = list(arm_res["seeds"].values())
    if len(rows) == len(seeds) and len(rows) == 5:
        agg = {k: round(sum(r[k] for r in rows) / len(rows), 4)
               for k in ("ledger_err", "naive_err",
                         "ledger_derived_err", "naive_derived_err",
                         "extract_calls", "abstentions")}
        agg["total_quizzes"] = sum(r["quizzes"] for r in rows)
        arm_res["aggregate"] = agg
        json.dump(res, open(RESULTS, "w"), indent=1)
        print(f"[{a.arm}] aggregate: {agg}", flush=True)
    print("FOLD-DOWNSTREAM-DONE", flush=True)


if __name__ == "__main__":
    main()
