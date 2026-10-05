"""Classical (non-LLM) stance baselines for the model fold (fastText,
CPU-only, deterministic). Two formulations:

PRIMARY - sentence-only stance: classify a pool sentence alone as
ASSERT or DENY (its stance toward its own fact). This is the classical
comparator for the LLM pipelines' stance stage given correct topic
identification (topic ID does not transfer across corpora - their fact
sets are disjoint by design). Train on the authored corpora (INDIE +
FREETEXT + COUNTERFACTUAL), test on REALWIRE + REALWIRE-T.

SECONDARY - pair model: classify (fact statement, sentence) pairs as
ASSERT / DENY / NEITHER, NEITHER pairs built CROSS-sentence (statement
of one fact, sentence of another) and class-balanced. The naive
construction (same sentence repeated under NEITHER with wrong facts)
was measured first and collapsed to never predicting ASSERT - the
sentence's own ngrams become anti-correlated with its true label; that
result is preserved in the results file as construction_v1.

Config (stated in advance, single configuration, no tuning):
fastText supervised, dim 100, epoch 50, lr 0.5, wordNgrams 2,
minCount 1, loss softmax, thread 1, seed 20261005.

Also computes, from the STANCE-02 census checkpoint, the LLM Arm A
stance accuracy conditioned on correct fact identification - the
number the primary baseline is compared against.
"""
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fasttext  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = 20261005
CFG = dict(dim=100, epoch=50, lr=0.5, wordNgrams=2, minCount=1,
           loss="softmax", thread=1, seed=SEED, verbose=0)


def norm_facts(module_facts):
    out = []
    for f in module_facts:
        if isinstance(f, dict):
            out.append((f["statement"], list(f["assert"]), list(f["deny"])))
        else:
            out.append((f[0], list(f[1]), list(f[2])))
    return out


def clean(sentence):
    s = sentence.split("] ", 1)[1] if "] " in sentence else sentence
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip().lower()


def train_model(rows, tag):
    path = os.path.join(HERE, f"fasttext_{tag}.txt")
    with open(path, "w") as fh:
        for text, label in rows:
            fh.write(f"__label__{label} {text}\n")
    return fasttext.train_supervised(path, **CFG)


def sentence_only(train_facts, test_facts):
    rows = []
    for _, apool, dpool in train_facts:
        rows += [(clean(s), "ASSERT") for s in apool]
        rows += [(clean(s), "DENY") for s in dpool]
    random.Random(SEED).shuffle(rows)
    model = train_model(rows, "sent_train")
    out = {}
    for pool_name, idx in (("assert", 1), ("deny", 2)):
        sel = [clean(s) for facts in test_facts for s in facts[idx]]
        want = "ASSERT" if pool_name == "assert" else "DENY"
        preds = model.predict(sel)[0]
        ok = sum(1 for pr in preds if pr[0] == "__label__" + want)
        out[pool_name] = {"n": len(sel), "correct": ok,
                          "accuracy": round(ok / len(sel), 4)}
    return out


def pair_model(train_facts, test_facts):
    def rows_for(facts):
        rng = random.Random(SEED)
        rows, cross = [], []
        sents = [(i, s, "ASSERT") for i, (_, a, _) in enumerate(facts)
                 for s in a]
        sents += [(i, s, "DENY") for i, (_, _, d) in enumerate(facts)
                  for s in d]
        for i, s, lab in sents:
            rows.append((f"{clean(facts[i][0])} ||| {clean(s)}", lab))
            j = rng.choice([k for k in range(len(facts)) if k != i])
            cross.append((f"{clean(facts[j][0])} ||| {clean(s)}",
                          "NEITHER"))
        n = max(sum(1 for _, l in rows if l == "ASSERT"),
                sum(1 for _, l in rows if l == "DENY"))
        rows += rng.sample(cross, min(n, len(cross)))
        rng.shuffle(rows)
        return rows

    model = train_model(rows_for(train_facts), "pair_train")
    out = {}
    test_rows = rows_for(test_facts)
    for lab in ("ASSERT", "DENY", "NEITHER"):
        sel = [t for (t, l) in test_rows if l == lab]
        preds = model.predict(sel)[0]
        ok = sum(1 for pr in preds if pr[0] == "__label__" + lab)
        out[lab.lower()] = {"n": len(sel), "correct": ok,
                            "accuracy": round(ok / len(sel), 4)}
    return out


def llm_conditional_stance():
    ckpt_path = os.path.join(HERE, "stance02_checkpoint.json")
    if not os.path.exists(ckpt_path):
        return {}
    ck = json.load(open(ckpt_path))
    out = {}
    for corpus in ("realwire", "realwire_t"):
        items = list(ck.get(f"A:{corpus}", {}).values())
        sel = [r for r in items if r.get("fact") == r.get("gold_fact")]
        ok = sum(1 for r in sel
                 if (r["stance"] == "ASSERT") == (r["gold_pool"] == "assert"))
        if sel:
            out[corpus] = {"n": len(sel), "correct": ok,
                           "accuracy": round(ok / len(sel), 4)}
    return out


def main():
    import counterfactual_corpus as cf
    import freetext_corpus as ft
    import indie_corpus as ic
    import realwire_corpus as rc
    import realwire_t_corpus as rct

    authored = (norm_facts(ic.INDIE_FACTS) + norm_facts(ft.FREE_FACTS)
                + norm_facts(cf.COUNTERFACTUAL_FACTS))
    results = {"config": {k: v for k, v in CFG.items() if k != "verbose"},
               "construction_v1_note": (
                   "naive pair construction (same sentence repeated "
                   "under NEITHER) collapsed: REALWIRE assert 0/59, "
                   "deny 2/72; superseded by the balanced cross-sentence "
                   "construction and the sentence-only primary.")}
    for name, facts in (("realwire", norm_facts(rc.REALWIRE_FACTS)),
                        ("realwire_t", norm_facts(rct.REALWIRET_FACTS))):
        so = sentence_only(authored, facts)
        pm = pair_model(authored, facts)
        results[name] = {"sentence_only": so, "pair_model": pm}
        print(f"{name} sentence-only: assert={so['assert']['correct']}/"
              f"{so['assert']['n']} ({so['assert']['accuracy']:.3f}) "
              f"deny={so['deny']['correct']}/{so['deny']['n']} "
              f"({so['deny']['accuracy']:.3f})", flush=True)
        print(f"{name} pair-model: " + "  ".join(
            f"{k}={v['correct']}/{v['n']} ({v['accuracy']:.3f})"
            for k, v in pm.items()), flush=True)
    results["llm_armA_stance_given_correct_fact_qwen3_8b"] = \
        llm_conditional_stance()
    print("llm conditional:", results[
        "llm_armA_stance_given_correct_fact_qwen3_8b"], flush=True)
    out = os.path.join(HERE, "fasttext_baseline_results.json")
    json.dump(results, open(out, "w"), indent=1)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
