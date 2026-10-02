"""Local-extraction validation (LOCAL-EXTRACTION-01) — decisive run.

The OpenRouter decisive run (5 seeds x 60 steps, ~$0.20) was blocked
on account balance (CONSOLIDATION-01). This runs the SAME protocol
with a free local model instead: Qwen3-8B (Q4_K_M) served by llama.cpp
on the owner's desktop, via newsroom.LocalExtractor.

Part 1 — parsing accuracy: the identical 200-sentence protocol
(seed 7) GPT-4o-mini scored 200/200 on; the modeled extractor assumed
0.85-0.95.

Part 2 — end-to-end, decisive form: seeds 0-4 x 60 steps with the
local extractor (shared by both agents), plus the modeled-extractor
baseline at the same seeds for reference. Note the standing caveat
from CONSOLIDATION-01: the modeled extractor consumes RNG draws the
LLM ones don't, so report streams are matched in distribution, not
identical — the 5-seed aggregate is the discriminator.

Checkpointed: results JSON is rewritten after every seed; re-running
skips completed seeds. Run unbuffered (python3 -u) on the desktop.
"""

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsroom import (FACTS, N_FACTS, SOURCES, LocalExtractor,  # noqa: E402
                      run_trial)

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "llm_extract_local_results.json")


def _load():
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            return json.load(f)
    return {}


def _save(res):
    with open(RESULTS, "w") as f:
        json.dump(res, f, indent=1)


def part1(res, n=200, seed=7):
    if "part1" in res:
        print(f"part 1: already done {res['part1']}", flush=True)
        return
    rng = random.Random(seed)
    jobs = []
    for _ in range(n):
        i = rng.randrange(N_FACTS)
        value = rng.random() < 0.5
        sent = rng.choice(FACTS[i][1 if value else 2])
        name = rng.choice(SOURCES)[0]
        jobs.append((f"[{name}] {sent}", name, i, value))
    ext = LocalExtractor()

    def work(job):
        text, name, i, value = job
        fi, sv = ext.extract(text, name)
        return (fi == i, sv == value)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(work, jobs))
    correct = sum(1 for f, v in results if f and v)
    fact_wrong = sum(1 for f, v in results if not f)
    value_wrong = sum(1 for f, v in results if f and not v)
    res["part1"] = {"accuracy": correct / n, "n": n,
                    "fact_wrong": fact_wrong, "value_wrong": value_wrong,
                    "calls": ext.calls, "seconds": round(time.time() - t0, 1)}
    _save(res)
    print(f"part 1: extraction accuracy {correct}/{n} = {correct / n:.3f} "
          f"(fact wrong: {fact_wrong}, value flipped: {value_wrong}) "
          f"calls={ext.calls} in {res['part1']['seconds']}s", flush=True)


def part2(res, seeds=(0, 1, 2, 3, 4), steps=60):
    res.setdefault("local_seeds", {})
    res.setdefault("modeled_seeds", {})
    for seed in seeds:
        key = str(seed)
        if key not in res["local_seeds"]:
            holder = {}

            def factory(rng, _h=holder):
                _h["ext"] = LocalExtractor()
                return _h["ext"]

            t0 = time.time()
            le, ne, q, lde, nde, *_ = run_trial(
                seed, steps=steps, extractor_factory=factory)
            res["local_seeds"][key] = {
                "ledger_err": le, "naive_err": ne, "quizzes": q,
                "ledger_derived_err": lde, "naive_derived_err": nde,
                "extract_calls": holder["ext"].calls,
                "seconds": round(time.time() - t0, 1)}
            _save(res)
            print(f"part 2 seed {seed} (local): ledger={le:.3f} "
                  f"naive={ne:.3f} derived {lde:.3f}/{nde:.3f} "
                  f"quizzes={q} calls={holder['ext'].calls} "
                  f"in {res['local_seeds'][key]['seconds']}s", flush=True)
        if key not in res["modeled_seeds"]:
            t0 = time.time()
            le, ne, q, lde, nde, *_ = run_trial(seed, steps=steps)
            res["modeled_seeds"][key] = {
                "ledger_err": le, "naive_err": ne, "quizzes": q,
                "ledger_derived_err": lde, "naive_derived_err": nde,
                "seconds": round(time.time() - t0, 1)}
            _save(res)
            print(f"part 2 seed {seed} (modeled): ledger={le:.3f} "
                  f"naive={ne:.3f} derived {lde:.3f}/{nde:.3f} "
                  f"quizzes={q}", flush=True)
    for label in ("local_seeds", "modeled_seeds"):
        rows = list(res[label].values())
        if len(rows) == len(seeds):
            agg = {k: round(sum(r[k] for r in rows) / len(rows), 4)
                   for k in ("ledger_err", "naive_err",
                             "ledger_derived_err", "naive_derived_err")}
            agg["total_quizzes"] = sum(r["quizzes"] for r in rows)
            res[f"{label}_aggregate"] = agg
            print(f"part 2 {label} aggregate: {agg}", flush=True)
    _save(res)


if __name__ == "__main__":
    res = _load()
    part1(res)
    part2(res)
    print("DONE", flush=True)
