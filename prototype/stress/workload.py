"""Trigger-discipline stress test for the living epistemic ledger.

Builds a synthetic, seeded workload: N claims in a random DAG, then a stream
of facts, each attached as a supporter to a random subset of claims. For each
fact the revisit loop runs twice on two identically-seeded ledgers — once
with the epsilon under test, once with epsilon=0 as the oracle — and the two
are compared.

Ground truth: a claim *should* be revisited iff its true (oracle) |delta|
>= materiality. Metrics per epsilon:
  - trigger recall    = should-revisit claims actually recomputed
  - precision         = recomputed claims that were should-revisit
                        (1 - precision = over-invalidation / wasted work)
  - flag volume       = materiality flags per fact
  - runtime

Usage:  python workload.py   (prints JSON results for the epsilon sweep)
"""

import json
import os
import random
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ledger import Ledger  # noqa: E402


def build_ledger(seed, n_claims, n_facts):
    """Two calls with the same seed produce structurally identical ledgers
    (claim i in one corresponds to claim i in the other)."""
    rng = random.Random(seed)
    d = tempfile.mkdtemp(prefix="ledger-stress-")
    L = Ledger(d)
    claims = []
    for i in range(n_claims):
        cid = L.assert_claim(
            f"claim-{i:04d}", prior=rng.uniform(0.2, 0.8),
            materiality=0.05, entrenchment=rng.uniform(0.0, 1.0))
        claims.append(cid)
        n_sup = rng.randint(0, min(3, i))  # supporters only from earlier claims -> DAG
        for s in rng.sample(claims[:-1], n_sup) if n_sup else []:
            kind = rng.choice(["deductive", "evidential", "evidential",
                               "human-asserted"])
            L.add_support(cid, s, kind,
                          p_given=rng.uniform(0.6, 0.99),
                          p_given_not=rng.uniform(0.01, 0.4))
    facts = []
    for k in range(n_facts):
        cred = rng.uniform(0.55, 0.99)
        fact = L.assert_claim(f"fact-{k:03d}", prior=cred, entrenchment=1.0)
        for dep in rng.sample(claims, rng.randint(1, 5)):
            L.add_support(dep, fact, "evidential",
                          p_given=rng.uniform(0.6, 0.99),
                          p_given_not=rng.uniform(0.01, 0.4))
        facts.append((fact, cred))
    pos = {cid: i for i, cid in enumerate(claims)}
    return L, d, facts, pos


def measure_epsilon(epsilon, seed=42, n_claims=300, n_facts=40,
                    materiality=0.05):
    Ls, ds, facts_s, pos_s = build_ledger(seed, n_claims, n_facts)
    Lo, do, facts_o, pos_o = build_ledger(seed, n_claims, n_facts)
    per_fact = []
    t0 = time.time()
    for k in range(n_facts):
        fs, cred = facts_s[k]
        fo, _ = facts_o[k]
        rs = Ls._revisit(fs, {fs: cred}, epsilon=epsilon)
        ro = Lo._revisit(fo, {fo: cred}, epsilon=0.0)  # oracle: no cutoff
        truth = {pos_o[u["claim_id"]] for u in ro["updates"]
                 if abs(u["delta"]) >= materiality}
        got = {pos_s[u["claim_id"]] for u in rs["updates"]}
        tp = len(truth & got)
        per_fact.append({
            "fact": k,
            "closure": rs["closure_size"],
            "n_truth": len(truth),
            "n_revisited": len(got),
            "recall": tp / len(truth) if truth else 1.0,
            "precision": tp / len(got) if got else 1.0,
            "flags": len(rs["flags"]),
        })
    wall = time.time() - t0
    shutil.rmtree(ds)
    shutil.rmtree(do)
    return {
        "epsilon": epsilon,
        "seed": seed,
        "n_claims": n_claims,
        "n_facts": n_facts,
        "materiality": materiality,
        "mean_recall": sum(f["recall"] for f in per_fact) / n_facts,
        "mean_precision": sum(f["precision"] for f in per_fact) / n_facts,
        "mean_flags": sum(f["flags"] for f in per_fact) / n_facts,
        "max_flags": max(f["flags"] for f in per_fact),
        "mean_closure": sum(f["closure"] for f in per_fact) / n_facts,
        "wall_seconds": round(wall, 2),
        "per_fact": per_fact,
    }


if __name__ == "__main__":
    out = [measure_epsilon(e) for e in (0.0, 0.005, 0.01, 0.02, 0.05)]
    # determinism check: same seed must give identical aggregates
    again = measure_epsilon(0.01)
    assert again["mean_recall"] == out[2]["mean_recall"], "non-deterministic!"
    assert again["mean_precision"] == out[2]["mean_precision"], "non-deterministic!"
    print(json.dumps(out, indent=1))
