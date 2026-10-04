"""STANCE-02 downstream payoff: REALWIRE newsroom Part 2 with each
candidate stance mechanism as the extractor (protocol frozen in
docs/STANCE-02.md; methodology identical to REALWIRE-01 Part 2:
seeds 0-4 x 60 steps, shared extraction, reference ledger error
0.4637 for the production baseline).

Adapters return (fact, says_true); a mechanism abstention (NEITHER /
ABSTAIN / error) returns (-1, False), which the newsroom's existing
ingest path drops and counts - the adapter also counts abstentions
itself so coverage loss per mechanism is reported.

Arm S downstream masks ONLINE (same masking prompt as the census
mask construction): newsroom sentences are generated live, so no
pre-built masks exist for them. Stages per item: topic (production
extract on the original sentence, stance discarded), mask, stance
on the masked sentence, recombine.

Checkpointed per (arm, seed). Local arms run on the desktop
(B/D need the thinking server configuration); EA runs anywhere.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import newsroom  # noqa: E402
from newsroom import LocalExtractor, run_trial  # noqa: E402
import realwire_corpus as rc  # noqa: E402
import stance02  # noqa: E402
from stance02_masks import MASK_PROMPT  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "stance02_downstream_results.json")
FACTS = [(s, list(a), list(d)) for (s, a, d) in rc.REALWIRE_FACTS]
FACTS_BLOCK = "\n".join(f"{i}. {s}" for i, (s, _, _) in enumerate(FACTS))


def strip_prefix(sentence):
    return (sentence.split("] ", 1)[1] if "] " in sentence
            else sentence)


class Adapter:
    def __init__(self):
        self.calls = 0
        self.abstentions = 0

    def _finish(self, rec):
        self.calls += 1
        if rec.get("stance") in ("ASSERT", "DENY") \
                and rec.get("fact", -1) >= 0:
            return rec["fact"], rec["stance"] == "ASSERT"
        self.abstentions += 1
        return -1, False

    def extract(self, sentence, source):
        raise NotImplementedError


class BaselineThinkAdapter(Adapter):
    def extract(self, sentence, source):
        rec = stance02.run_single(
            "B", FACTS_BLOCK, sentence,
            lambda p: stance02.local_chat(p, think=True,
                                          max_tokens=12000))
        return self._finish(rec)


class StructuredAdapter(Adapter):
    def __init__(self, think):
        super().__init__()
        self.think = think
        self.arm = "D" if think else "C"
        self.mt = 12000 if think else 256

    def extract(self, sentence, source):
        rec = stance02.run_structured(
            self.arm, FACTS, FACTS_BLOCK, sentence,
            lambda p: stance02.local_chat(p, think=self.think,
                                          max_tokens=self.mt))
        return self._finish(rec)


class SkeletonAdapter(Adapter):
    def __init__(self):
        super().__init__()
        newsroom.FACTS = rc.REALWIRE_FACTS
        self.topic_ex = LocalExtractor()

    def extract(self, sentence, source):
        self.calls += 1
        body = strip_prefix(sentence)
        try:
            tfact, _ = self.topic_ex.extract(sentence, source)
            if tfact < 0:
                self.abstentions += 1
                return -1, False
            stmt = FACTS[tfact][0]
            masked, _, _ = stance02.local_chat(
                MASK_PROMPT.format(stmt=stmt, sent=body),
                max_tokens=300)
            masked = masked.strip().strip('"')
            if "[PROPOSITION X]" not in masked:
                self.abstentions += 1
                return -1, False
            prompt = ("A claim, called Proposition X, is discussed "
                      f'in this sentence: "{masked}"\n\n'
                      "Does the sentence assert that Proposition X "
                      "is TRUE, or that it is FALSE, or neither? "
                      "Return ONLY JSON: "
                      '{"stance": "TRUE"|"FALSE"|"NEITHER"}')
            text, _, _ = stance02.local_chat(prompt, max_tokens=64)
            d = stance02.parse_json(text, ("stance",))
            s = str(d["stance"]).upper()
            if s == "TRUE":
                return tfact, True
            if s == "FALSE":
                return tfact, False
            self.abstentions += 1
            return -1, False
        except Exception:
            self.abstentions += 1
            return -1, False


class HostedBaselineAdapter(Adapter):
    def extract(self, sentence, source):
        rec = stance02.run_single(
            "EA", FACTS_BLOCK, sentence,
            lambda p: stance02.hosted_chat(p))
        return self._finish(rec)


FACTORIES = {
    "B": lambda: BaselineThinkAdapter(),
    "C": lambda: StructuredAdapter(False),
    "D": lambda: StructuredAdapter(True),
    "S": lambda: SkeletonAdapter(),
    "EA": lambda: HostedBaselineAdapter(),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices=list(FACTORIES))
    ap.add_argument("--seeds", default="0,1,2,3,4")
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",")]
    newsroom.FACTS = rc.REALWIRE_FACTS
    res = {}
    if os.path.exists(RESULTS):
        res = json.load(open(RESULTS))
    arm_res = res.setdefault(a.arm, {"seeds": {}})
    for seed in seeds:
        key = str(seed)
        if key in arm_res["seeds"]:
            print(f"[{a.arm}] seed {seed} already done", flush=True)
            continue
        holder = {}

        def factory(rng, _h=holder):
            _h["ext"] = FACTORIES[a.arm]()
            return _h["ext"]

        t0 = time.time()
        le, ne, q, lde, nde, *_ = run_trial(
            seed, steps=60, extractor_factory=factory)
        arm_res["seeds"][key] = {
            "ledger_err": le, "naive_err": ne, "quizzes": q,
            "ledger_derived_err": lde, "naive_derived_err": nde,
            "extract_calls": holder["ext"].calls,
            "abstentions": holder["ext"].abstentions,
            "seconds": round(time.time() - t0, 1)}
        json.dump(res, open(RESULTS, "w"), indent=1)
        print(f"[{a.arm}] seed {seed}: ledger={le:.4f} naive={ne:.4f} "
              f"derived={lde:.4f}/{nde:.4f} calls="
              f"{holder['ext'].calls} abst={holder['ext'].abstentions} "
              f"({arm_res['seeds'][key]['seconds']}s)", flush=True)
    rows = list(arm_res["seeds"].values())
    if len(rows) == 5:
        agg = {k: round(sum(r[k] for r in rows) / len(rows), 4)
               for k in ("ledger_err", "naive_err",
                         "ledger_derived_err", "naive_derived_err",
                         "extract_calls", "abstentions")}
        agg["total_quizzes"] = sum(r["quizzes"] for r in rows)
        arm_res["aggregate"] = agg
        json.dump(res, open(RESULTS, "w"), indent=1)
        print(f"[{a.arm}] aggregate: {agg}", flush=True)
    print("DOWNSTREAM-DONE", flush=True)


if __name__ == "__main__":
    main()
