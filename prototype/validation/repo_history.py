"""Real-domain validation: dogfood the ledger on its own git history.

The epistemic-ledger repo is a real, evolving codebase. Factual claims about
it (epsilon default, test count, which features exist) have objective ground
truth recoverable per-commit via `git show`. We replay the repo's history as
an observation stream:

  ledger-backed: fact claims observed per commit; revisit loop (with
                 noisy-and combos) re-scores derived judgments.
  naive:         facts observed; derived judgments frozen at the first
                 commit's values (the "stale memory" baseline).

Derived judgments are AND-structured ("v0.3 complete" iff learned
entrenchment AND D-S intervals AND context experiment all exist), which
exercises the v0.4 joint-likelihood machinery on real data.

Metric: derived-judgment accuracy vs. git ground truth, ledger vs. naive.
Observation noise (10% misread) models an agent that occasionally reads
the repo wrong; credence 0.95.

Usage: python repo_history.py   (run from the repo root or anywhere;
        locates the repo via this file's path)
"""

import os
import random
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ledger import Ledger  # noqa: E402

REPO = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", ".."))

STATES = [  # (sha or None for working tree, label)
    ("30ea54c", "v0.1 prototype"),
    ("495bb34", "trigger stress test"),
    ("460b97a", "v0.2 contradiction resolution"),
    ("46d8b50", "v0.3 entrenchment + D-S + context exp"),
    ("ab5dbd3", "source verification pass"),
    (None, "working tree (v0.4 joint likelihoods)"),
]


def _git(*args):
    r = subprocess.run(["git", "-C", REPO, *args],
                       capture_output=True, text=True)
    return r


def _content(sha, path):
    """File content at a state; None if missing."""
    if sha is None:
        p = os.path.join(REPO, path)
        try:
            with open(p) as f:
                return f.read()
        except FileNotFoundError:
            return None
    r = _git("show", f"{sha}:{path}")
    return r.stdout if r.returncode == 0 else None


def _exists(sha, path):
    return _content(sha, path) is not None


def extract_facts(sha):
    """Ground-truth facts about the repo at one state. All measurable."""
    ledger_src = _content(sha, "prototype/ledger.py") or ""
    tests_src = _content(sha, "prototype/tests/test_ledger.py") or ""
    m = re.search(r"epsilon=([\d.]+)\):", ledger_src)
    m2 = re.search(r"materiality=([\d.]+),\s*critical", ledger_src)
    n_tests = len(re.findall(r"^def test_", tests_src, re.M))
    return {
        "epsilon_is_0005": (m.group(1) == "0.005") if m else None,
        "materiality_is_005": (m2.group(1) == "0.05") if m2 else None,
        "tests_ge_14": n_tests >= 14,
        "contradiction_resolution": "resolve_contradiction" in ledger_src,
        "learned_entrenchment": "learn_entrenchment" in ledger_src,
        "ds_intervals": "combine_interval" in ledger_src,
        "context_experiment": _exists(sha, "prototype/context/experiment.py"),
        "trigger_stress": _exists(sha, "docs/TRIGGER-STRESS-01.md"),
        "bibliography": _exists(sha, "docs/research/BIBLIOGRAPHY.md"),
        "joint_likelihoods": "set_combo" in ledger_src,
    }


DERIVED = {
    "trigger_discipline_tuned": ["epsilon_is_0005", "trigger_stress"],
    "contradiction_shipped": ["contradiction_resolution"],
    "v03_complete": ["learned_entrenchment", "ds_intervals",
                     "context_experiment"],
    "research_verified": ["bibliography"],
    "joint_shipped": ["joint_likelihoods"],
}


class RepoAgent:
    """Ledger-backed agent tracking the repo over time."""

    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="repohist-")
        self.L = Ledger(self.dir)
        self.facts = {}
        self.derived = {}

    def setup(self, fact_names):
        for f in fact_names:
            self.facts[f] = self.L.assert_claim(f"repo fact: {f}", 0.5)
        for d, inputs in DERIVED.items():
            did = self.L.assert_claim(f"derived judgment: {d}", 0.5)
            for f in inputs:
                self.L.add_support(did, self.facts[f], "evidential")
            self.L.set_combo(did, "noisy-and")
            self.derived[d] = did

    def observe(self, name, value, credence):
        cid = self.facts[name]
        score = credence if value else 1.0 - credence
        if abs(score - self.L._live_claim(cid)["score"]) < 1e-12:
            return
        self.L._set_score(cid, score, None, actor="agent")
        self.L._revisit(cid, {cid: score}, actor="agent")

    def answer(self, d):
        return self.L._live_claim(self.derived[d])["score"] > 0.5

    def close(self):
        shutil.rmtree(self.dir)


def run(seed=0, noise=0.1, credence=0.95):
    rng = random.Random(seed)
    truth = [extract_facts(sha) for sha, _ in STATES]
    assert all(v is not None for facts in truth for v in facts.values()), \
        "unmeasurable fact — extractor bug"

    agent = RepoAgent()
    agent.setup(list(truth[0]))
    naive_facts = {}
    naive_derived = {}
    ledger_err = naive_err = quizzes = 0

    for i, (facts, (sha, label)) in enumerate(zip(truth, STATES)):
        for name, v in facts.items():
            obs = v if rng.random() > noise else not v  # misread model
            agent.observe(name, obs, credence)
            naive_facts[name] = obs
        if i == 0:
            for d, inputs in DERIVED.items():
                naive_derived[d] = all(naive_facts[f] for f in inputs)
        for d, inputs in DERIVED.items():
            t = all(facts[f] for f in inputs)
            quizzes += 1
            ledger_err += agent.answer(d) != t
            naive_err += naive_derived[d] != t
    agent.close()
    return ledger_err / quizzes, naive_err / quizzes, quizzes


if __name__ == "__main__":
    print("state truth table:")
    for (sha, label), facts in zip(STATES,
                                   [extract_facts(s) for s, _ in STATES]):
        row = " ".join("1" if v else "0" for v in facts.values())
        print(f"  {label:42s} {row}")
    print(f"\n  facts: {' '.join(extract_facts(None))}\n")
    ls, ns = [], []
    for seed in range(5):
        le, ne, q = run(seed)
        ls.append(le)
        ns.append(ne)
        print(f"seed {seed}: ledger_err={le:.3f} naive_err={ne:.3f}")
    l, n = sum(ls) / 5, sum(ns) / 5
    print(f"\n[{q} quizzes] mean ledger_err={l:.3f} mean naive_err={n:.3f}")
    print(f"staleness reduction = {n - l:.3f} "
          f"({(n - l) / n * 100:.1f}% of naive errors eliminated)")
