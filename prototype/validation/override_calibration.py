"""OVERRIDE-CAL-01 — calibrate the override_rate kill bar with a
scripted human in the loop.

KILL-BARS-01 left override_rate (bar 0.20) UNMEASURED: every
automated workload records 0.0 because nothing ever calls
manual_score. This harness puts a *scripted reviewer* — a simulated
human editor with a stated cadence, deviation threshold, and
reliability — inside the standard newsroom trial via run_trial's
reviewer hook, and measures three things:

  1. the override_rate a plausible reviewer actually produces
     (is 0.20 a sensible bar, and at what cadence does it trip?),
  2. whether human overrides help or hurt ledger error, and
  3. the propagation gap: manual_score sets a score but does not
     revisit dependents, so a diligent+propagate variant (which
     mirrors the ingest path's _revisit call) isolates what that
     costs on derived claims.

Personas are simulations, not humans. Any bar conclusion is
therefore about the instrument's response curve, and the report
says so. Baseline (reviewer=None) must reproduce the archived
modeled numbers exactly before any persona result is read.
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation.newsroom import run_trial, CONTESTED  # noqa: E402

TARGET = {True: 0.9, False: 0.1}


def in_scope_claims(agent):
    """Claims with ground truth: fact claims + contested desk claims."""
    out = {}
    for i, cid in agent.facts.items():
        out[cid] = i
    for (i, _desk), cid in agent.desks.items():
        out[cid] = i
    return out


class Reviewer:
    """Base: on cadence steps, correct claims deviating from truth."""

    def __init__(self, seed, cadence=5, threshold=0.35, reliability=1.0,
                 error_rate=0.0, propagate=False, worst_only=False):
        self.rng = random.Random(seed)
        self.cadence = cadence
        self.threshold = threshold
        self.reliability = reliability
        self.error_rate = error_rate
        self.propagate = propagate
        self.worst_only = worst_only
        self.n_calls = 0

    def __call__(self, agent, cur, step):
        if step % self.cadence != 0:
            return
        cands = []
        for cid, i in in_scope_claims(agent).items():
            score = agent.L.get_score(cid)
            dev = abs(score - (1.0 if cur[i] else 0.0))
            if dev > self.threshold:
                cands.append((dev, cid, i))
        cands.sort(reverse=True)
        if self.worst_only:
            cands = cands[:1]
        for _dev, cid, i in cands:
            if self.rng.random() > self.reliability:
                continue
            truth = cur[i]
            if self.rng.random() < self.error_rate:
                truth = not truth  # fallible human: corrects the wrong way
            val = TARGET[truth]
            # No explicit t: mirror the newsroom agent's own convention
            # (wall-clock _now()). Two versions of one claim at the same
            # logical t violate the (claim_id, txn_from) PK — recorded
            # as a finding in the OVERRIDE-CAL-01 report.
            agent.L.manual_score(cid, val)
            self.n_calls += 1
            if self.propagate:
                agent.L._revisit(cid, {cid: val}, actor="human")


PERSONAS = {
    "diligent":        dict(cadence=5, threshold=0.35, reliability=0.9),
    "diligent+prop":   dict(cadence=5, threshold=0.35, reliability=0.9,
                            propagate=True),
    "spot":            dict(cadence=10, threshold=0.5, worst_only=True),
    "noisy":           dict(cadence=5, threshold=0.35, reliability=1.0,
                            error_rate=0.20),
    "diligent-cad1":   dict(cadence=1, threshold=0.35, reliability=0.9),
    "diligent-cad15":  dict(cadence=15, threshold=0.35, reliability=0.9),
}

SEEDS = range(5)


def run_config(name, kwargs):
    rows = []
    for seed in SEEDS:
        rev = Reviewer(10_000 + seed, **kwargs)
        le, ne, q, lde, nde, _s, _a, meta = run_trial(seed, reviewer=rev)
        rows.append({"seed": seed, "ledger_err": le, "naive_err": ne,
                     "ledger_derived_err": lde,
                     "override_rate": meta["override_rate"],
                     "n_manual_overrides": meta["n_manual_overrides"],
                     "reviewer_calls": rev.n_calls,
                     "breached": meta["breached"]})
    agg = {k: sum(r[k] for r in rows) / len(rows)
           for k in ("ledger_err", "ledger_derived_err", "override_rate",
                     "n_manual_overrides")}
    return {"persona": name, "per_seed": rows, "mean": agg}


def main():
    base = []
    for seed in SEEDS:
        le, ne, q, lde, nde, _s, _a, meta = run_trial(seed)
        base.append({"seed": seed, "ledger_err": le, "naive_err": ne,
                     "ledger_derived_err": lde,
                     "override_rate": meta["override_rate"]})
    b0 = base[0]
    assert abs(b0["ledger_err"] - 0.140625) < 1e-9, b0
    print(f"baseline verified: seed0 {b0['ledger_err']:.6f}; "
          f"mean ledger {sum(r['ledger_err'] for r in base)/5:.4f}")

    results = {"baseline": base, "personas": []}
    for name, kwargs in PERSONAS.items():
        cfg = run_config(name, kwargs)
        results["personas"].append(cfg)
        m = cfg["mean"]
        print(f"{name:16s} ledger {m['ledger_err']:.4f} "
              f"derived {m['ledger_derived_err']:.4f} "
              f"override_rate {m['override_rate']:.4f} "
              f"(manual {m['n_manual_overrides']:.1f}/trial)")

    out = Path(__file__).with_name("override_calibration_results.json")
    out.write_text(json.dumps(results, indent=1))
    print(f"wrote {out.name}")


if __name__ == "__main__":
    main()
