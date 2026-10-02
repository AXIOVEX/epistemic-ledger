"""Free-text validation (FREETEXT-01).

Every prior extraction/newsroom number was measured on the 2+2
template sentences in newsroom.FACTS. This replaces them with the
authored free-prose pools in freetext_corpus.FREE_FACTS (same 12
facts, statements identical; 6 true + 6 false renderings per fact,
ground truth by construction) and re-measures with the same local
extractor (Qwen3-8B, llama.cpp on the owner's desktop, $0).

Part 1 — extraction census: every pooled sentence exactly once
(144), plus scored HARD_PROBES (denials of claims, double
negations, dismissals of negations), unscored OBSERVATIONS
(mentions without commitment — outputs recorded verbatim), and
DISTRACTORS (no fact asserted; any output is a forced misparse
under the forced-choice contract).

Part 2 — end-to-end: newsroom.FACTS is rebound to the free pools
and run_trial runs seeds 0-4 x 60 steps with the local extractor,
exactly as LOCAL-EXTRACTION-01 ran the template pools (its
results, llm_extract_local_results.json, are the comparison
anchor: same extractor, same seeds, only the prose differs).

Checkpointed after every part/seed; re-running skips completed
work. Run unbuffered (python3 -u) on the desktop.
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
import freetext_corpus as fc  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "freetext_local_results.json")


def _load():
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            return json.load(f)
    return {}


def _save(res):
    with open(RESULTS, "w") as f:
        json.dump(res, f, indent=1)


def _jobs():
    jobs = []  # (kind, sentence, fact_or_None, value_or_None)
    k = 0
    for i, (_, trues, falses) in enumerate(fc.FREE_FACTS):
        for s in trues:
            jobs.append(("pool", s, i, True))
        for s in falses:
            jobs.append(("pool", s, i, False))
    for s, i, v in fc.HARD_PROBES:
        jobs.append(("hard", s, i, v))
    for s in fc.OBSERVATIONS:
        jobs.append(("observation", s, None, None))
    for s in fc.DISTRACTORS:
        jobs.append(("distractor", s, None, None))
    out = []
    for kind, s, i, v in jobs:
        name = SOURCES[k % len(SOURCES)][0]
        k += 1
        out.append((kind, f"[{name}] {s}", name, i, v))
    return out


def part1(res):
    if "part1" in res:
        print(f"part 1: already done", flush=True)
        return
    ext = LocalExtractor()
    jobs = _jobs()

    def work(job):
        kind, text, name, i, v = job
        try:
            fi, sv = ext.extract(text, name)
            return (kind, text, i, v, fi, sv, None)
        except Exception as e:  # a raise is a result, not a crash
            return (kind, text, i, v, None, None,
                    f"{type(e).__name__}: {e}")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(work, jobs))
    p1 = {"seconds": round(time.time() - t0, 1), "calls": ext.calls}
    for kind in ("pool", "hard"):
        sel = [r for r in rows if r[0] == kind]
        ok = sum(1 for r in sel if r[6] is None and r[4] == r[2]
                 and r[5] == r[3])
        p1[kind] = {
            "n": len(sel), "correct": ok,
            "accuracy": round(ok / len(sel), 4),
            "fact_wrong": sum(1 for r in sel if r[6] is None
                              and r[4] != r[2]),
            "value_wrong": sum(1 for r in sel if r[6] is None
                               and r[4] == r[2] and r[5] != r[3]),
            "errors": sum(1 for r in sel if r[6] is not None),
            "failures": [
                {"sentence": r[1], "expected": [r[2], r[3]],
                 "got": [r[4], r[5]], "error": r[6]}
                for r in sel
                if not (r[6] is None and r[4] == r[2] and r[5] == r[3])],
        }
        print(f"part 1 {kind}: {ok}/{len(sel)} = {ok / len(sel):.3f}",
              flush=True)
    p1["observations"] = [
        {"sentence": r[1], "got": [r[4], r[5]], "error": r[6]}
        for r in rows if r[0] == "observation"]
    p1["distractors"] = [
        {"sentence": r[1], "mapped_to_fact": r[4],
         "says_true": r[5], "error": r[6]}
        for r in rows if r[0] == "distractor"]
    print(f"part 1 distractors: "
          f"{sum(1 for d in p1['distractors'] if d['error'] is None)}"
          f"/{len(p1['distractors'])} force-mapped to some fact",
          flush=True)
    res["part1"] = p1
    _save(res)


def part2(res, seeds=(0, 1, 2, 3, 4), steps=60):
    newsroom.FACTS = fc.FREE_FACTS  # rebind: free prose pools
    res.setdefault("freetext_seeds", {})
    for seed in seeds:
        key = str(seed)
        if key in res["freetext_seeds"]:
            continue
        holder = {}

        def factory(rng, _h=holder):
            _h["ext"] = LocalExtractor()
            return _h["ext"]

        t0 = time.time()
        le, ne, q, lde, nde, *_ = run_trial(
            seed, steps=steps, extractor_factory=factory)
        res["freetext_seeds"][key] = {
            "ledger_err": le, "naive_err": ne, "quizzes": q,
            "ledger_derived_err": lde, "naive_derived_err": nde,
            "extract_calls": holder["ext"].calls,
            "seconds": round(time.time() - t0, 1)}
        _save(res)
        print(f"part 2 seed {seed} (freetext): ledger={le:.3f} "
              f"naive={ne:.3f} derived {lde:.3f}/{nde:.3f} "
              f"quizzes={q} calls={holder['ext'].calls} "
              f"in {res['freetext_seeds'][key]['seconds']}s",
              flush=True)
    rows = list(res["freetext_seeds"].values())
    if len(rows) == len(seeds):
        agg = {k: round(sum(r[k] for r in rows) / len(rows), 4)
               for k in ("ledger_err", "naive_err",
                         "ledger_derived_err", "naive_derived_err")}
        agg["total_quizzes"] = sum(r["quizzes"] for r in rows)
        res["freetext_aggregate"] = agg
        print(f"part 2 freetext aggregate: {agg}", flush=True)
    _save(res)


if __name__ == "__main__":
    assert all(fc.FREE_FACTS[i][0] == newsroom.FACTS[i][0]
               for i in range(len(fc.FREE_FACTS))), \
        "free corpus statements must match newsroom.FACTS"
    res = _load()
    part1(res)
    part2(res)
    print("DONE", flush=True)
