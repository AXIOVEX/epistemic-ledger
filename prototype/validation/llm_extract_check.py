"""LLM extraction check (CONSOLIDATION-01) — v2, checkpointed.

Part 1 — parsing accuracy: 200 generated sentences with known
(fact, value); LLMExtractor must recover both. Run 8-way parallel.
Compared against the modeled misparse rates (PARSE_ACC 0.85–0.95)
the simulation assumed.

Part 2 — end-to-end smoke check: one 10-step newsroom seed with the
LLM extractor swapped in (shared by both agents), vs. the same
seed/steps with the modeled extractor.

Run unbuffered (python3 -u); every line flushes so a timeout cannot
eat the results. (v1 lost everything to stdout buffering at a 550s
timeout after spending $0.0218 — that failure is recorded in the
CONSOLIDATION-01 report.)
"""

import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from newsroom import (FACTS, N_FACTS, SOURCES, LLMExtractor, run_trial)  # noqa: E402


def part1(n=200, seed=7):
    rng = random.Random(seed)
    jobs = []
    for _ in range(n):
        i = rng.randrange(N_FACTS)
        value = rng.random() < 0.5
        sent = rng.choice(FACTS[i][1 if value else 2])
        name = rng.choice(SOURCES)[0]
        jobs.append((f"[{name}] {sent}", name, i, value))
    ext = LLMExtractor()
    results = []

    def work(job):
        text, name, i, value = job
        fi, sv = ext.extract(text, name)
        return (fi == i, sv == value)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, jobs))
    correct = sum(1 for f, v in results if f and v)
    fact_wrong = sum(1 for f, v in results if not f)
    value_wrong = sum(1 for f, v in results if f and not v)
    print(f"part 1: extraction accuracy {correct}/{n} = {correct / n:.3f} "
          f"(fact wrong: {fact_wrong}, value flipped: {value_wrong}) "
          f"spend=${ext.client.spent:.4f} calls={ext.client.calls}",
          flush=True)


def part2(steps=10):
    holder = {}

    def factory(rng):
        holder["ext"] = LLMExtractor()
        return holder["ext"]

    le, ne, q, lde, nde, stats, accs, meta = run_trial(
        0, steps=steps, extractor_factory=factory)
    print(f"part 2 (LLM extractor, {steps} steps): ledger={le:.3f} "
          f"naive={ne:.3f} derived {lde:.3f}/{nde:.3f} quizzes={q} "
          f"spend=${holder['ext'].client.spent:.4f}", flush=True)
    le2, ne2, q2, lde2, nde2, *_ = run_trial(0, steps=steps)
    print(f"part 2 (modeled extractor, same seed): ledger={le2:.3f} "
          f"naive={ne2:.3f} derived {lde2:.3f}/{nde2:.3f} quizzes={q2}",
          flush=True)


if __name__ == "__main__":
    part1()
    part2()
    print("DONE", flush=True)
