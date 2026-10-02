"""Independent-corpus validation (INDIE-CORPUS-01).

FREETEXT-01's named caveat: its corpus shared an author with the
system under test. This corpus was authored by a different model
family (OpenAI gpt-4.1, via indie_generate.py) — every sentence —
and measured with the identical protocol: Part 1 extraction census
over the 144 pooled sentences, Part 2 newsroom (seeds 0-4 x 60
steps, newsroom.FACTS rebound to the indie pools) with the local
extractor on the owner's desktop. Template (LOCAL-EXTRACTION-01)
and FREETEXT-01 results are the comparison anchors.

Checkpointed; run unbuffered (python3 -u) on the desktop.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import newsroom  # noqa: E402
from newsroom import SOURCES, LocalExtractor, run_trial  # noqa: E402
import indie_corpus as ic  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "indie_local_results.json")


def _load():
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            return json.load(f)
    return {}


def _save(res):
    with open(RESULTS, "w") as f:
        json.dump(res, f, indent=1)


def part1(res):
    if "part1" in res:
        print("part 1: already done", flush=True)
        return
    ext = LocalExtractor()
    jobs = []
    k = 0
    for i, (_, trues, falses) in enumerate(ic.INDIE_FACTS):
        for s in trues:
            jobs.append((f"[{SOURCES[k % len(SOURCES)][0]}] {s}", i, True))
            k += 1
        for s in falses:
            jobs.append((f"[{SOURCES[k % len(SOURCES)][0]}] {s}", i, False))
            k += 1

    def work(job):
        text, i, v = job
        try:
            fi, sv = ext.extract(text, None)
            return (text, i, v, fi, sv, None)
        except Exception as e:
            return (text, i, v, None, None, f"{type(e).__name__}: {e}")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(work, jobs))
    ok = sum(1 for r in rows if r[5] is None and r[3] == r[1]
             and r[4] == r[2])
    res["part1"] = {
        "n": len(rows), "correct": ok,
        "accuracy": round(ok / len(rows), 4),
        "fact_wrong": sum(1 for r in rows if r[5] is None
                          and r[3] != r[1]),
        "value_wrong": sum(1 for r in rows if r[5] is None
                           and r[3] == r[1] and r[4] != r[2]),
        "errors": sum(1 for r in rows if r[5] is not None),
        "seconds": round(time.time() - t0, 1), "calls": ext.calls,
        "failures": [
            {"sentence": r[0], "expected": [r[1], r[2]],
             "got": [r[3], r[4]], "error": r[5]}
            for r in rows
            if not (r[5] is None and r[3] == r[1] and r[4] == r[2])]}
    _save(res)
    print(f"part 1 pool: {ok}/{len(rows)} = {ok / len(rows):.3f}",
          flush=True)


def part2(res, seeds=(0, 1, 2, 3, 4), steps=60):
    newsroom.FACTS = ic.INDIE_FACTS
    res.setdefault("indie_seeds", {})
    for seed in seeds:
        key = str(seed)
        if key in res["indie_seeds"]:
            continue
        holder = {}

        def factory(rng, _h=holder):
            _h["ext"] = LocalExtractor()
            return _h["ext"]

        t0 = time.time()
        le, ne, q, lde, nde, *_ = run_trial(
            seed, steps=steps, extractor_factory=factory)
        res["indie_seeds"][key] = {
            "ledger_err": le, "naive_err": ne, "quizzes": q,
            "ledger_derived_err": lde, "naive_derived_err": nde,
            "extract_calls": holder["ext"].calls,
            "seconds": round(time.time() - t0, 1)}
        _save(res)
        print(f"part 2 seed {seed} (indie): ledger={le:.3f} "
              f"naive={ne:.3f} derived {lde:.3f}/{nde:.3f} "
              f"quizzes={q} calls={holder['ext'].calls} "
              f"in {res['indie_seeds'][key]['seconds']}s", flush=True)
    rows = list(res["indie_seeds"].values())
    if len(rows) == len(seeds):
        agg = {k: round(sum(r[k] for r in rows) / len(rows), 4)
               for k in ("ledger_err", "naive_err",
                         "ledger_derived_err", "naive_derived_err")}
        agg["total_quizzes"] = sum(r["quizzes"] for r in rows)
        res["indie_aggregate"] = agg
        print(f"part 2 indie aggregate: {agg}", flush=True)
    _save(res)


if __name__ == "__main__":
    assert all(ic.INDIE_FACTS[i][0] == newsroom.FACTS[i][0]
               for i in range(len(ic.INDIE_FACTS)))
    res = _load()
    part1(res)
    part2(res)
    print("DONE", flush=True)
