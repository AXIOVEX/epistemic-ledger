"""STANCE-03 candidate: Arm F - split call 1.

STANCE-02's decomposition found the structured protocol's largest
local coverage sink was call-1 topic abdication: the compound first
call (fact + discourse act + attribution + corrective in one JSON)
returns fact -1 on 17-34% of items, so the commitment probes never
run. Arm F differs from Arm C in exactly one component: the topic is
identified by the proven baseline extraction call (stance02.run_single
arm A - the production prompt), and only the two symmetric commitment
probes (prompt text copied verbatim from stance02.run_structured)
plus the frozen deterministic derivation are kept. The discourse-act
fields are dropped - they never influenced the derivation.

This is a POST-FREEZE development measurement (STANCE-02 is closed);
it reuses the frozen corpora, scoring (stance02.score_cell), probe
prompts, and derivation, unchanged. Checkpointed per corpus.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import stance02  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(HERE, "stance03_checkpoint.json")
RESULTS = os.path.join(HERE, "stance03_results.json")


def run_split(facts, facts_block, sentence, chat):
    body = (sentence.split("] ", 1)[1] if "] " in sentence
            else sentence)
    topic = stance02.run_single("A", facts_block, sentence, chat)
    fact = topic["fact"]
    lat = topic.get("latency", 0.0)
    rec = {"fact": fact, "topic_stance": topic.get("stance")}
    if fact < 0 or fact >= len(facts):
        rec.update({"stance": "ABSTAIN", "stage": "topic",
                    "latency": lat})
        return rec
    stmt = facts[fact][0]
    answers = {}
    for tag, ques in (
            ("P", "personally commit to the truth of P"),
            ("notP", "personally commit to P being FALSE")):
        pq = (f"Sentence: \"{body}\"\n\nProposition P: \"{stmt}\"\n\n"
              f"Does the WRITER of this sentence {ques}? Judge the "
              "writer's commitment as expressed in the text - not "
              "whether P is actually true, and not what any person "
              "quoted or mentioned in the sentence believes. If the "
              "writer reports someone else's commitment without "
              "taking a position, the writer does not commit. Return "
              "ONLY JSON: {\"answer\": \"yes\"|\"no\"|\"unclear\", "
              "\"confidence\": <0..1>}")
        t2, dt, _u = chat(pq)
        lat += dt
        d2 = stance02.parse_json(t2, ("answer",))
        answers[tag] = str(d2["answer"]).lower()
        rec[f"commits_{tag}"] = answers[tag]
        rec[f"confidence_{tag}"] = d2.get("confidence")
    rec["stance"] = stance02.derive(answers["P"], answers["notP"])
    rec["latency"] = lat
    return rec


def run_cell(corpus_name):
    facts, meta = stance02.load_corpus(corpus_name)
    jobs = []
    for i, (_, apool, dpool) in enumerate(facts):
        for s in apool:
            jobs.append((i, "assert", s))
        for s in dpool:
            jobs.append((i, "deny", s))
    facts_block = "\n".join(f"{i}. {s}"
                            for i, (s, _, _) in enumerate(facts))
    ckpt = {}
    if os.path.exists(CKPT):
        ckpt = json.load(open(CKPT))
    key = f"F:{corpus_name}"
    done = ckpt.get(key, {})
    todo = [(j, job) for j, job in enumerate(jobs)
            if str(j) not in done]
    print(f"[{key}] {len(jobs)} sentences, {len(todo)} remaining",
          flush=True)
    for n, (j, (i, pool, sent)) in enumerate(todo):
        try:
            rec = run_split(facts, facts_block, sent,
                            lambda p: stance02.local_chat(
                                p, max_tokens=256))
        except Exception as e:
            rec = {"fact": -1, "stance": "ABSTAIN",
                   "error": f"{type(e).__name__}: {e}", "latency": 0.0}
        done[str(j)] = rec
        if (n + 1) % 20 == 0 or n + 1 == len(todo):
            ckpt[key] = done
            json.dump(ckpt, open(CKPT, "w"), indent=1)
            print(f"  {n + 1}/{len(todo)}", flush=True)
    ckpt[key] = done
    json.dump(ckpt, open(CKPT, "w"), indent=1)
    scored = stance02.score_cell(jobs, done, meta)
    res = {}
    if os.path.exists(RESULTS):
        res = json.load(open(RESULTS))
    res[key] = scored
    json.dump(res, open(RESULTS, "w"), indent=1)
    print(f"[{key}] acc={scored['accuracy']:.3f} "
          f"cov={scored['coverage']:.3f} "
          f"assert={scored['pools']['assert']['accuracy']:.3f} "
          f"deny={scored['pools']['deny']['accuracy']:.3f} "
          f"gap={scored.get('bias_gap', 0):.3f}", flush=True)
    return scored


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora", default="realwire,realwire_t,indie")
    a = ap.parse_args()
    for name in a.corpora.split(","):
        run_cell(name.strip())
    print("STANCE03-CENSUS-DONE", flush=True)


if __name__ == "__main__":
    main()
