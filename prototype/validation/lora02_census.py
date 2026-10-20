"""LORA-02 one-shot census (frozen design: docs/LORA-02.md).

Arm A protocol against a llama-server endpoint serving either L0
(production Q4_K_M) or L1 (winner merged Q4_K_M). Corpora: heldout
and dev-format JSON ({facts:[{statement,assert,deny}]}), plus the
program corpora realwire / realwire_t / indie / freetext via their
own modules. One run per (model, corpus); no retries, no reseeding.

Usage: lora01_census.py --base-url http://localhost:8084/v1
       --tag L0 --corpora heldout,realwire,realwire_t,indie,freetext
Output: lora02_census_<tag>.json next to this file (checkpointed
per corpus; abstentions = parse failure or fact < 0).
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stance02  # noqa: E402  (baseline_prompt, run_single, local_chat)

HERE = Path(__file__).parent
JSON_CORPORA = {"heldout": "lora02_heldout.json",
                "dev": "lora02_dev.json"}


def load_json_corpus(path):
    data = json.loads(Path(path).read_text())
    return [(f["statement"], list(f["assert"]), list(f["deny"]))
            for f in data["facts"]]


def load_named(name):
    if name in JSON_CORPORA:
        return load_json_corpus(HERE / JSON_CORPORA[name])
    if name == "freetext":
        from freetext_corpus import FREE_FACTS
        return [(f[0], list(f[1]), list(f[2])) for f in FREE_FACTS]
    facts, _meta = stance02.load_corpus(name)
    return facts


def score(facts, results):
    pools = {"assert": [0, 0], "deny": [0, 0]}
    abstain = errors = 0
    for r in results:
        pool = "assert" if r["says_true_want"] else "deny"
        pools[pool][1] += 1
        pred = r["pred"]
        if pred is None:
            errors += 1
        elif pred["stance"] == "ABSTAIN" or pred["fact"] < 0:
            abstain += 1
        elif (pred["fact"] == r["fact"]
              and (pred["stance"] == "ASSERT") == r["says_true_want"]):
            pools[pool][0] += 1
    a = pools["assert"][0] / max(1, pools["assert"][1])
    d = pools["deny"][0] / max(1, pools["deny"][1])
    tot = (pools["assert"][0] + pools["deny"][0]) / max(
        1, pools["assert"][1] + pools["deny"][1])
    return {"assert_acc": a, "deny_acc": d, "total_acc": tot,
            "gap": abs(a - d), "abstentions": abstain,
            "parse_errors": errors,
            "n": pools["assert"][1] + pools["deny"][1]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--corpora", required=True)
    args = ap.parse_args()
    stance02.LOCAL_URL = args.base_url.rstrip("/") + "/chat/completions"
    out_path = HERE / f"lora02_census_{args.tag}.json"
    done = {}
    if out_path.exists():
        done = json.loads(out_path.read_text())
    for name in args.corpora.split(","):
        if name in done:
            print(f"skip {name} (checkpointed)", flush=True)
            continue
        facts = load_named(name)
        block = "\n".join(f"{i}. {s}" for i, (s, _, _) in
                          enumerate(facts))
        results = []
        t0 = time.time()
        for fi, (_s, apool, dpool) in enumerate(facts):
            for pool, want in ((apool, True), (dpool, False)):
                for sent in pool:
                    try:
                        pred = stance02.run_single(
                            "A", block, sent, stance02.local_chat)
                    except Exception:
                        pred = None
                    results.append({"fact": fi,
                                    "says_true_want": want,
                                    "pred": pred})
        cell = score(facts, results)
        cell["wall_s"] = round(time.time() - t0, 1)
        cell["records"] = results
        done[name] = cell
        out_path.write_text(json.dumps(done, indent=1))
        print(f"{args.tag}:{name} total {cell['total_acc']:.3f} "
              f"assert {cell['assert_acc']:.3f} deny {cell['deny_acc']:.3f} "
              f"gap {cell['gap']:.3f} abst {cell['abstentions']} "
              f"err {cell['parse_errors']}", flush=True)
    print("CENSUS-DONE", args.tag)


if __name__ == "__main__":
    main()
