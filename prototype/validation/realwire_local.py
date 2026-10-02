"""Real published-copy validation (REALWIRE-01).

FREETEXT-01 and INDIE-CORPUS-01 both measured extraction on
authored sentences (system author, then gpt-4.1). This corpus is
verbatim published copy -- news, wire, reference, book, and
periodical sentences asserting or denying 12 real-world
propositions (see realwire_corpus.py for sourcing, attribution,
and the QC drops). Identical protocol: Part 1 extraction census
over the 131 pooled sentences, Part 2 newsroom (seeds 0-4 x 60
steps, newsroom.FACTS rebound to the realwire pools) with the
local extractor on the owner's desktop. Comparison anchors:
FREETEXT-01 (Part 1 0.972; ledger/naive 16.8%; derived 43.5%)
and INDIE-CORPUS-01 (0.972; 21.1%; 49.7%).

The realwire statements intentionally differ from the fictional
newsroom facts; the machinery only needs 12 fact indices, so the
statement-identity assert used by the indie runner does not
apply here.

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
import realwire_corpus as rc  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "realwire_local_results.json")


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
    # LocalExtractor snapshots the fact list at construction; rebind
    # BEFORE constructing it or the census runs against the fictional
    # newsroom facts. (The indie runner needed no rebind: its
    # statements were identical to newsroom.FACTS.)
    newsroom.FACTS = rc.REALWIRE_FACTS
    ext = LocalExtractor()
    jobs = []
    k = 0
    for i, (_, trues, falses) in enumerate(rc.REALWIRE_FACTS):
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
    newsroom.FACTS = rc.REALWIRE_FACTS
    res.setdefault("realwire_seeds", {})
    for seed in seeds:
        key = str(seed)
        if key in res["realwire_seeds"]:
            continue
        holder = {}

        def factory(rng, _h=holder):
            _h["ext"] = LocalExtractor()
            return _h["ext"]

        t0 = time.time()
        le, ne, q, lde, nde, *_ = run_trial(
            seed, steps=steps, extractor_factory=factory)
        res["realwire_seeds"][key] = {
            "ledger_err": le, "naive_err": ne, "quizzes": q,
            "ledger_derived_err": lde, "naive_derived_err": nde,
            "extract_calls": holder["ext"].calls,
            "seconds": round(time.time() - t0, 1)}
        _save(res)
        print(f"part 2 seed {seed} (realwire): ledger={le:.3f} "
              f"naive={ne:.3f} derived {lde:.3f}/{nde:.3f} "
              f"quizzes={q} calls={holder['ext'].calls} "
              f"in {res['realwire_seeds'][key]['seconds']}s", flush=True)
    rows = list(res["realwire_seeds"].values())
    if len(rows) == len(seeds):
        agg = {k: round(sum(r[k] for r in rows) / len(rows), 4)
               for k in ("ledger_err", "naive_err",
                         "ledger_derived_err", "naive_derived_err")}
        agg["total_quizzes"] = sum(r["quizzes"] for r in rows)
        res["realwire_aggregate"] = agg
        print(f"part 2 realwire aggregate: {agg}", flush=True)
    _save(res)


if __name__ == "__main__":
    assert len(rc.REALWIRE_FACTS) == newsroom.N_FACTS == 12
    res = _load()
    part1(res)
    part2(res)
    print("DONE", flush=True)
