"""OVERRIDE-CAL-02 — human calibration of the override_rate kill bar.

OVERRIDE-CAL-01 calibrated the bar against scripted reviewers that
peek at ground truth. This runner puts a HUMAN in the same loop:
identical newsroom workload, identical cadence discipline, identical
metrics — but the reviewer sees only the reports the system received
and the scores it holds, never the truth. Protocol and verdict rules
are frozen in docs/OVERRIDE-CAL-02.md.

Mechanics:
- The reviewer hook fires every 5 steps (cadence). At each point the
  reviewer is shown the 14 reviewable claims (10 facts + 4 desk
  assessments) with current scores, the reports received since the
  last review (source + stance as written), and the system's learned
  source accuracies. Overrides go through the real human path,
  Ledger.manual_score.
- Every decision is persisted to the results JSON the moment it is
  made. If a session stops mid-seed, rerunning replays the recorded
  decisions silently (the modeled trial is deterministic, so replay
  reaches the identical state) and prompting resumes at the first
  unrecorded review point.
- Baseline gate: before the first session, seed 0 with no reviewer
  must reproduce OVERRIDE-CAL-01's archived number exactly
  (ledger_err 0.140625), as that study required of itself.

Usage:
    python3 override_calibration_human.py --reviewer <name>
    python3 override_calibration_human.py --reviewer <name> --seeds 3,4
    python3 override_calibration_human.py --report
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from validation.newsroom import (  # noqa: E402
    CONTESTED, FACTS, SOURCES, ModeledExtractor, run_trial)

RESULTS_PATH = Path(__file__).with_name(
    "override_calibration_human_results.json")
TIER_OF = {n: t for n, t, _, _ in SOURCES}

INSTRUCTIONS = """\
You are the editor reviewing this ledger's beliefs. Every 5 steps you
will see each claim, its current score (the system's probability that
it is TRUE), and the reports received since your last review, shown as
source:stance (T = the sentence asserted the claim, F = it denied it).
Two sources are unregistered rumor sources; the system's learned
accuracy estimate for every source is shown at each review.

To change a score, enter number=value pairs, e.g.  3=0.9 11=0.1
(score will be set to that probability). Press Enter alone to keep
everything. Type q to save and stop; you can resume later and will
never be asked the same review twice. Correct what the evidence says
is wrong; leave what it supports."""


class SessionQuit(Exception):
    pass


class LoggingExtractor(ModeledExtractor):
    """ModeledExtractor that records the report stream as written
    (topic + expressed stance + source), before parse noise, so the
    human reviewer can be shown the evidence the system received."""

    def __init__(self, rng):
        super().__init__(rng)
        self.log = []

    def extract(self, sentence, source):
        body = sentence.split("] ", 1)[1] if "] " in sentence else sentence
        fact_id, as_written = self.registry[body]
        out = super().extract(sentence, source)
        self.log.append({"source": source, "fact": fact_id,
                         "says": as_written})
        return out


def ordered_claims(agent):
    """The 14 reviewable claims in display order: facts by index,
    then the desk assessments of the contested facts."""
    out = []
    for i in sorted(agent.facts):
        out.append((agent.facts[i], FACTS[i][0]))
    for (i, desk) in sorted(agent.desks):
        out.append((agent.desks[(i, desk)],
                    f"[{desk}-desk assessment] {FACTS[i][0]}"))
    return out


class HumanReviewer:
    def __init__(self, session, save, cadence=5):
        self.session = session          # {"decisions": [entry, ...]}
        self.save = save                # persist callback
        self.cadence = cadence
        self.log = None                 # extractor log (set on 1st call)
        self.pointer = 0                # reports already presented
        self.n_applied = 0

    # -- evidence digest -------------------------------------------------
    def _digest(self, agent, items):
        by_cid = {}
        for it in items:
            i = it["fact"]
            if i in CONTESTED:
                desk = "wire" if TIER_OF[it["source"]] else "rumor"
                cid = agent.desks[(i, desk)]
            else:
                cid = agent.facts[i]
            by_cid.setdefault(cid, []).append(
                f"{it['source']}:{'T' if it['says'] else 'F'}")
        return by_cid

    # -- the hook ---------------------------------------------------------
    def __call__(self, agent, cur, step):  # cur = ground truth: NEVER read
        if self.log is None:
            self.log = agent.extractor.log
        if step % self.cadence != 0:
            return
        items = self.log[self.pointer:]
        recorded = {e["step"]: e for e in self.session["decisions"]}
        if step in recorded:  # replay: apply silently, ask nothing
            # Claim ids are minted fresh every trial, so a recorded
            # override is replayed by its stable display number (the
            # ordered claim list is identical across runs), never by
            # the id it carried in the recording run.
            claims = ordered_claims(agent)
            for ov in recorded[step]["overrides"]:
                cid = claims[ov["n"] - 1][0]
                agent.L.manual_score(cid, ov["value"])
                self.n_applied += 1
            self.pointer = len(self.log)
            return
        claims = ordered_claims(agent)
        digest = self._digest(agent, items)
        print(f"\n=== Review: step {step} of 60 "
              f"({len(items)} reports since last review) ===")
        acc = "  ".join(f"{n} {agent.acc[n]:.2f}" for n in agent.acc)
        print(f"Learned source accuracy: {acc}")
        for n, (cid, label) in enumerate(claims, 1):
            reps = " ".join(digest.get(cid, [])) or "(no reports)"
            print(f"{n:2d}. score {agent.L.get_score(cid):.2f}  {label}")
            print(f"    reports: {reps}")
        overrides = self._ask(claims, agent)
        entry = {"step": step,
                 "at": datetime.now(timezone.utc).isoformat(),
                 "reports_seen": len(items),
                 "overrides": overrides}
        self.session["decisions"].append(entry)
        self.pointer = len(self.log)
        self.save()
        for ov in overrides:
            agent.L.manual_score(ov["cid"], ov["value"])
            self.n_applied += 1

    def _ask(self, claims, agent):
        while True:
            try:
                line = input("Overrides (number=value, blank = keep "
                             "all, q = save + quit): ").strip()
            except EOFError:
                raise SessionQuit
            if line.lower() == "q":
                raise SessionQuit
            if not line:
                return []
            try:
                out = []
                for tok in line.split():
                    n, v = tok.split("=", 1)
                    idx, val = int(n), float(v)
                    if not (1 <= idx <= len(claims)):
                        raise ValueError(f"no claim {idx}")
                    if not (0.0 <= val <= 1.0):
                        raise ValueError("value must be in [0, 1]")
                    cid = claims[idx - 1][0]
                    out.append({"n": idx, "cid": cid, "value": val,
                                "old": agent.L.get_score(cid)})
                return out
            except ValueError as e:
                print(f"  not applied ({e}); try again")


# ----------------------------------------------------------------------
# session bookkeeping
# ----------------------------------------------------------------------

def load_results(path):
    if path.exists():
        return json.loads(path.read_text())
    return {"study": "OVERRIDE-CAL-02", "sessions": {}}


def save_results(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, path)


def baseline_gate():
    le, *_rest = run_trial(0)
    assert abs(le - 0.140625) < 1e-9, f"baseline drift: {le}"
    print(f"baseline verified: seed 0 ledger_err {le:.6f} "
          f"(OVERRIDE-CAL-01 archived value)")


def run_seed(data, path, reviewer_name, seed, cadence):
    key = f"{reviewer_name}::seed{seed}"
    session = data["sessions"].setdefault(
        key, {"reviewer": reviewer_name, "seed": seed,
              "cadence": cadence, "decisions": [], "result": None})
    if session["result"] is not None:
        print(f"seed {seed}: already complete for {reviewer_name}; "
              f"skipping")
        return
    rev = HumanReviewer(session, lambda: save_results(path, data),
                        cadence=cadence)
    factory = lambda rng: LoggingExtractor(rng)  # noqa: E731
    t0 = time.time()
    try:
        (le, ne, _q, lde, nde, _s, _a, meta) = run_trial(
            seed, extractor_factory=factory, reviewer=rev)
    except SessionQuit:
        save_results(path, data)
        done = len(session["decisions"])
        print(f"\nsaved. Seed {seed} has {done} review points recorded; "
              f"rerun the same command to resume where you stopped.")
        raise
    session["result"] = {
        "ledger_err": le, "naive_err": ne,
        "ledger_derived_err": lde, "naive_derived_err": nde,
        "override_rate": meta["override_rate"],
        "n_manual_overrides": meta["n_manual_overrides"],
        "reviewer_overrides_applied": rev.n_applied,
        "breached": meta["breached"],
        "wall_s": round(time.time() - t0, 1),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    save_results(path, data)
    r = session["result"]
    print(f"seed {seed} done: ledger {le:.4f} (naive {ne:.4f}) "
          f"derived {lde:.4f} override_rate {r['override_rate']:.4f} "
          f"manual {r['n_manual_overrides']}")


def report(path):
    data = load_results(path)
    done = [(k, s) for k, s in sorted(data["sessions"].items())
            if s.get("result")]
    if not done:
        print("no completed sessions recorded yet")
        return
    print(f"{'session':28s} {'ledger':>7s} {'base':>7s} {'derived':>8s} "
          f"{'ovr_rate':>8s} {'manual':>6s}")
    for key, s in done:
        base_le, *_ = run_trial(s["seed"])
        r = s["result"]
        print(f"{key:28s} {r['ledger_err']:7.4f} {base_le:7.4f} "
              f"{r['ledger_derived_err']:8.4f} "
              f"{r['override_rate']:8.4f} "
              f"{r['n_manual_overrides']:6d}")
    print("\nreference (OVERRIDE-CAL-01, scripted): baseline mean "
          "0.1452 / derived 0.1450; diligent persona (cadence 5) "
          "0.0758 / 0.0858 at override_rate 0.0200; bar = 0.20")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviewer", help="reviewer name (records who)")
    ap.add_argument("--seeds", default="0,1,2",
                    help="comma list, default the primary arm 0,1,2")
    ap.add_argument("--cadence", type=int, default=5)
    ap.add_argument("--results", type=Path, default=RESULTS_PATH)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="baseline gate only")
    args = ap.parse_args()
    if args.report:
        report(args.results)
        return
    baseline_gate()
    if args.check:
        return
    if not args.reviewer:
        ap.error("--reviewer is required for a session")
    data = load_results(args.results)
    print(INSTRUCTIONS)
    try:
        for seed in [int(x) for x in args.seeds.split(",")]:
            run_seed(data, args.results, args.reviewer, seed,
                     args.cadence)
    except SessionQuit:
        return
    report(args.results)


if __name__ == "__main__":
    main()
