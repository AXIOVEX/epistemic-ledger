"""LLM context-cleanup experiment: does the ledger reduce memory staleness?

Simulated world of binary facts that flip over time. Derived conclusions
form single-parent chains (F -> D1 -> D2), so the ledger's per-edge Jeffrey
propagation is exact and both memories share identical semantics — the ONLY
difference is revision vs. frozen:

  ledger-backed: observations update fact claims; the revisit loop
                 automatically re-scores dependent conclusions.
  naive:         derived conclusions computed once from initial
                 observations; never revised (the "frozen context" baseline).

Metric: per-step error rate on derived questions vs. ground truth.
Staleness reduction = naive_error - ledger_error.

Design note: an earlier version used AND-structured derived beliefs, but
per-edge independent Jeffrey does not compose into AND (each edge pulls
toward the same posterior regardless of how many supporters hold). That is
a genuine expressiveness boundary of the v0.3 propagation model, recorded
in docs/CONTEXT-CLEANUP-01.md — not something this experiment should
confound with staleness.

Usage: python experiment.py
"""

import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ledger import Ledger  # noqa: E402


class World:
    def __init__(self, rng, n_facts, flip_p):
        self.rng = rng
        self.flip_p = flip_p
        self.facts = {f"F{i}": rng.random() < 0.5 for i in range(n_facts)}

    def step(self):
        for k in self.facts:
            if self.rng.random() < self.flip_p:
                self.facts[k] = not self.facts[k]


class AgentMemory:
    """Ledger-backed working memory."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="ctx-ledger-")
        self.L = Ledger(self.dir)
        self.fact_claims = {}
        self.derived = {}

    def setup(self, chains):
        # chains: [(fact_name, d1_name, d2_name), ...]
        for fname, d1, d2 in chains:
            self.fact_claims[fname] = self.L.assert_claim(f"world fact {fname}", 0.5)
            c1 = self.L.assert_claim(f"derived {d1}", 0.5)
            c2 = self.L.assert_claim(f"derived {d2}", 0.5)
            self.L.add_support(c1, self.fact_claims[fname], "deductive", 0.95, 0.05)
            self.L.add_support(c2, c1, "deductive", 0.95, 0.05)
            self.derived[d1] = c1
            self.derived[d2] = c2
        self.chains = chains

    def observe(self, name, value, credence):
        cid = self.fact_claims[name]
        score = credence if value else 1.0 - credence
        if abs(score - self.L._live_claim(cid)["score"]) < 1e-12:
            return
        self.L._set_score(cid, score, None, actor="agent")
        self.L._revisit(cid, {cid: score}, actor="agent")

    def answer(self, dname):
        return self.L._live_claim(self.derived[dname])["score"] > 0.5

    def close(self):
        shutil.rmtree(self.dir)


class NaiveMemory:
    """Frozen-context baseline: derived conclusions never revised."""

    def setup(self, chains, initial_obs):
        self.facts = dict(initial_obs)
        self.derived = {}
        for fname, d1, d2 in chains:
            v = self.facts[fname]
            self.derived[d1] = v
            self.derived[d2] = v

    def observe(self, name, value, credence):
        self.facts[name] = value  # facts update; derived do NOT

    def answer(self, dname):
        return self.derived[dname]


def run_trial(seed, n_chains=8, steps=60, flip_p=0.05, obs_p=0.5):
    rng = random.Random(seed)
    world = World(rng, n_chains, flip_p)
    fnames = list(world.facts)
    chains = [(fn, f"D1_{i}", f"D2_{i}") for i, fn in enumerate(fnames)]
    mem = AgentMemory()
    mem.setup(chains)
    naive = NaiveMemory()
    init = {}
    for name in fnames:  # initial observation sweep (noisy)
        v = world.facts[name]
        obs = v if rng.random() < 0.9 else not v
        init[name] = obs
        mem.observe(name, obs, 0.8)
    naive.setup(chains, init)

    ledger_err = naive_err = quizzes = 0
    for _ in range(steps):
        world.step()
        for name in fnames:
            if rng.random() < obs_p:
                v = world.facts[name]
                obs = v if rng.random() < 0.9 else not v
                mem.observe(name, obs, 0.8)
                naive.observe(name, obs, 0.8)
        for fname, d1, d2 in chains:
            truth = world.facts[fname]  # D1 = D2 = F by construction
            for d in (d1, d2):
                quizzes += 1
                ledger_err += mem.answer(d) != truth
                naive_err += naive.answer(d) != truth
    mem.close()
    return ledger_err / quizzes, naive_err / quizzes


if __name__ == "__main__":
    ls, ns = [], []
    for seed in range(5):
        le, ne = run_trial(seed)
        ls.append(le)
        ns.append(ne)
        print(f"seed {seed}: ledger_err={le:.3f} naive_err={ne:.3f}")
    l, n = sum(ls) / 5, sum(ns) / 5
    print(f"\nmean ledger_err={l:.3f} mean naive_err={n:.3f}")
    print(f"staleness reduction = {n - l:.3f} "
          f"({(n - l) / n * 100:.1f}% of naive errors eliminated)")
