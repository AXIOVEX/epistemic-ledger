"""STANCE-02 runner (protocol frozen in docs/STANCE-02.md).

Cells are (arm, corpus); one run per cell; checkpointed per item;
completed cells are final. Arms:
  A  production baseline (newsroom.LocalExtractor, verbatim)
  B  baseline prompt, thinking enabled (parse: last valid JSON)
  C  discourse-act + symmetric probing, deterministic derivation
  D  C with thinking enabled + discourse-only reasoning instruction
  S  STANCE-SKELETON pipeline (topic from original, stance on mask)
  EA hosted gpt-5.5-2026-04-23, baseline protocol, temp 0, effort none
  EC hosted, structured protocol (as C)

Every item records: fact guess, final stance (ASSERT/DENY/NEITHER/
ABSTAIN), error flag, latency seconds, arm-specific stage fields.
Scoring implements the frozen definitions from the study doc.
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import newsroom  # noqa: E402
from newsroom import LocalExtractor  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "stance02_results.json")
CKPT = os.path.join(HERE, "stance02_checkpoint.json")
MASKS = os.path.join(HERE, "skeleton_masks.json")
LOCAL_URL = "http://localhost:8083/v1/chat/completions"
HOSTED_MODEL = "gpt-5.5-2026-04-23"

ACTS = ("direct_assertion", "direct_denial", "attributed_assertion",
        "attributed_denial", "debunking_corrective",
        "discussion_no_commitment", "uncertain_other")
REASON_CONSTRAINT = ("Reason only about the sentence's wording, "
                     "structure, and who commits to what. Do not "
                     "reason about whether the proposition itself is "
                     "true or false. ")


# ------------------------------------------------------------------
# corpora
# ------------------------------------------------------------------
def load_corpus(name):
    """Return (facts, meta): facts = [(statement, assert, deny)]."""
    if name == "realwire":
        from realwire_corpus import REALWIRE_FACTS
        return [(s, list(a), list(d)) for (s, a, d) in REALWIRE_FACTS], {}
    if name == "realwire_t":
        from realwire_t_corpus import REALWIRET_FACTS
        return ([(f["statement"], list(f["assert"]), list(f["deny"]))
                 for f in REALWIRET_FACTS], {})
    if name == "indie":
        from indie_corpus import INDIE_FACTS
        return [(s, list(a), list(d)) for (s, a, d) in INDIE_FACTS], {}
    if name == "counterfactual":
        from counterfactual_corpus import COUNTERFACTUAL_FACTS
        facts = [(f["statement"], list(f["assert"]), list(f["deny"]))
                 for f in COUNTERFACTUAL_FACTS]
        meta = {i: {"tier": f["tier"], "truth": f["truth"]}
                for i, f in enumerate(COUNTERFACTUAL_FACTS)}
        return facts, meta
    raise ValueError(name)


# ------------------------------------------------------------------
# completion backends
# ------------------------------------------------------------------
def local_chat(prompt, think=False, max_tokens=64, system=None):
    import urllib.request
    body = json.dumps({
        "model": "qwen3-8b-local", "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system",
             "content": system or "You extract structured data. "
                                  "Return only JSON."},
            {"role": "user", "content": prompt}],
        "chat_template_kwargs": {"enable_thinking": think},
    }).encode()
    req = urllib.request.Request(
        LOCAL_URL, data=body,
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read())
    return (data["choices"][0]["message"]["content"],
            time.time() - t0, data.get("usage", {}))


def hosted_chat(prompt, max_tokens=800, system=None):
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    import dynamic_credentials as dc
    import urllib.request
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": HOSTED_MODEL, "temperature": 0,
        "reasoning_effort": "none",
        "max_completion_tokens": max_tokens,
        "messages": msgs}).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"Content-Type": "application/json"})
    dc.add_surrogate_to_request(req, "custom.openai",
                                allowed_hosts=["api.openai.com"])
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        data = dc.read_json_response(r)
    return (data["choices"][0]["message"]["content"],
            time.time() - t0, data.get("usage", {}))


def parse_json(text, keys, last=False):
    cands = re.findall(r"\{.*?\}", text, re.S)
    if last:
        cands = cands[::-1]
    for c in cands:
        try:
            d = json.loads(c)
        except Exception:
            continue
        if all(k in d for k in keys):
            return d
    raise ValueError(f"no JSON with keys {keys} in: {text[:120]!r}")


# ------------------------------------------------------------------
# arms A / B / EA (single-call stance classification)
# ------------------------------------------------------------------
def baseline_prompt(facts_block, body):
    return (f"Facts:\n{facts_block}\n\n"
            f'Sentence: "{body}"\n\n'
            "Which fact does the sentence report on, and does it "
            "assert that fact is TRUE or FALSE? Return ONLY JSON: "
            '{"fact": <index>, "says_true": <true|false>}')


def run_single(arm, facts_block, sentence, chat):
    body = (sentence.split("] ", 1)[1] if "] " in sentence
            else sentence)
    text, dt, usage = chat(baseline_prompt(facts_block, body))
    d = parse_json(text, ("fact", "says_true"), last=(arm in ("B",)))
    fact = int(d["fact"])
    if fact < 0:
        return {"fact": fact, "stance": "ABSTAIN", "latency": dt,
                "usage": usage}
    return {"fact": fact,
            "stance": "ASSERT" if d["says_true"] else "DENY",
            "latency": dt, "usage": usage}


# ------------------------------------------------------------------
# arms C / D / EC (structured: act + symmetric probes + derivation)
# ------------------------------------------------------------------
def derive(cp, cnp):
    if cp == "unclear" or cnp == "unclear":
        return "ABSTAIN"
    if cp == "yes" and cnp == "no":
        return "ASSERT"
    if cp == "no" and cnp == "yes":
        return "DENY"
    if cp == "no" and cnp == "no":
        return "NEITHER"
    return "ABSTAIN"  # yes/yes: incoherent pair


def run_structured(arm, facts, facts_block, sentence, chat):
    think = arm in ("D",)
    pre = REASON_CONSTRAINT if think else ""
    body = (sentence.split("] ", 1)[1] if "] " in sentence
            else sentence)
    lat = 0.0
    usage_tot = {}
    p1 = (f"{pre}Facts:\n{facts_block}\n\nSentence: \"{body}\"\n\n"
          "Answer three things about this sentence. (1) fact: the "
          "index of the fact the sentence is about, or -1 if none. "
          "(2) discourse_act: exactly one of " + ", ".join(ACTS) +
          ". (3) proposition_attributed_to_other: does the sentence "
          "present the proposition mainly as someone else's claim "
          "rather than the writer's own position (yes/no/unclear)? "
          "(4) corrective_or_debunking_act: is the sentence's act "
          "mainly to correct or debunk the proposition "
          "(yes/no/unclear)? Return ONLY JSON: {\"fact\": <index>, "
          "\"discourse_act\": \"<act>\", "
          "\"proposition_attributed_to_other\": \"<yes|no|unclear>\", "
          "\"corrective_or_debunking_act\": \"<yes|no|unclear>\"}")
    t1, dt, u1 = chat(p1)
    lat += dt
    d1 = parse_json(t1, ("fact", "discourse_act"), last=think)
    fact = int(d1["fact"])
    rec = {"fact": fact, "discourse_act": d1.get("discourse_act"),
           "attributed": d1.get("proposition_attributed_to_other"),
           "corrective": d1.get("corrective_or_debunking_act"),
           "usage": u1}
    if fact < 0 or fact >= len(facts):
        rec.update({"stance": "ABSTAIN", "latency": lat})
        return rec
    stmt = facts[fact][0]
    answers = {}
    for tag, ques in (
            ("P", "personally commit to the truth of P"),
            ("notP", "personally commit to P being FALSE")):
        pq = (f"{pre}Sentence: \"{body}\"\n\nProposition P: \"{stmt}\"\n\n"
              f"Does the WRITER of this sentence {ques}? Judge the "
              "writer's commitment as expressed in the text - not "
              "whether P is actually true, and not what any person "
              "quoted or mentioned in the sentence believes. If the "
              "writer reports someone else's commitment without "
              "taking a position, the writer does not commit. Return "
              "ONLY JSON: {\"answer\": \"yes\"|\"no\"|\"unclear\", "
              "\"confidence\": <0..1>}")
        t2, dt, u2 = chat(pq)
        lat += dt
        d2 = parse_json(t2, ("answer",), last=think)
        answers[tag] = str(d2["answer"]).lower()
        rec[f"commits_{tag}"] = answers[tag]
        rec[f"confidence_{tag}"] = d2.get("confidence")
    rec["stance"] = derive(answers["P"], answers["notP"])
    rec["latency"] = lat
    return rec


# ------------------------------------------------------------------
# arm S (skeleton pipeline)
# ------------------------------------------------------------------
def run_skeleton(facts, facts_block, sentence, key, masks, chat_local,
                 topic_extract):
    lat = 0.0
    t0 = time.time()
    try:
        tfact, ttrue = topic_extract(sentence)
    except Exception as e:
        return {"fact": -1, "stance": "ABSTAIN", "error_stage": "topic",
                "error": f"{type(e).__name__}: {e}", "latency": 0.0}
    lat += time.time() - t0
    rec = {"fact": tfact, "topic_says_true": ttrue}
    if tfact < 0:
        rec.update({"stance": "ABSTAIN", "latency": lat})
        return rec
    entry = masks.get(key)
    if entry is None:
        rec.update({"stance": "ABSTAIN", "error_stage": "mask",
                    "error": "no mask for item", "latency": lat})
        return rec
    if entry.get("degenerate"):
        rec.update({"stance": "EXCLUDED", "latency": lat})
        return rec
    masked = entry["masked"]
    prompt = ("A claim, called Proposition X, is discussed in this "
              f'sentence: "{masked}"\n\n'
              "Does the sentence assert that Proposition X is TRUE, "
              "or that it is FALSE, or neither? Return ONLY JSON: "
              '{"stance": "TRUE"|"FALSE"|"NEITHER"}')
    text, dt, usage = chat_local(prompt)
    lat += dt
    d = parse_json(text, ("stance",))
    s = str(d["stance"]).upper()
    rec["stance"] = {"TRUE": "ASSERT", "FALSE": "DENY"}.get(
        s, "ABSTAIN")
    rec["latency"] = lat
    rec["usage"] = usage
    return rec


# ------------------------------------------------------------------
# cell driver + frozen scoring
# ------------------------------------------------------------------
def score_cell(jobs, records, meta):
    out = {"n": 0, "excluded": 0, "correct": 0, "covered": 0,
           "abstained": 0, "errors": 0, "latency_total": 0.0,
           "pools": {}, "per_fact": {}, "per_tier": {}}
    for pool in ("assert", "deny"):
        out["pools"][pool] = {"n": 0, "correct": 0, "covered": 0,
                              "abstained": 0, "errors": 0}
    for j, (i, pool, sent) in enumerate(jobs):
        rec = records[str(j)]
        gold = "ASSERT" if pool == "assert" else "DENY"
        if rec.get("stance") == "EXCLUDED":
            out["excluded"] += 1
            continue
        out["n"] += 1
        out["latency_total"] += rec.get("latency", 0.0)
        p = out["pools"][pool]
        p["n"] += 1
        pf = out["per_fact"].setdefault(
            str(i), {"n": 0, "correct": 0, "covered": 0,
                     "abstained": 0, "errors": 0})
        pf["n"] += 1
        tier = meta.get(i, {}).get("tier") if meta else None
        pt = None
        if tier is not None:
            pt = out["per_tier"].setdefault(
                str(tier), {"n": 0, "correct": 0, "covered": 0,
                            "abstained": 0, "errors": 0,
                            "assert": {"n": 0, "correct": 0},
                            "deny": {"n": 0, "correct": 0}})
            pt["n"] += 1
            pt[pool]["n"] += 1
        covered = rec.get("stance") in ("ASSERT", "DENY")
        correct = covered and rec.get("fact") == i \
            and rec.get("stance") == gold
        for agg in (out, p, pf) + ((pt,) if pt else ()):
            if correct:
                agg["correct"] += 1
            if covered:
                agg["covered"] += 1
            else:
                agg["abstained"] += 1
            if "error" in rec:
                agg["errors"] += 1
        if pt and correct:
            pt[pool]["correct"] += 1
    for pool, p in out["pools"].items():
        p["accuracy"] = p["correct"] / p["n"] if p["n"] else None
        p["coverage"] = p["covered"] / p["n"] if p["n"] else None
        p["cond_accuracy"] = (p["correct"] / p["covered"]
                              if p["covered"] else None)
    out["accuracy"] = out["correct"] / out["n"] if out["n"] else None
    out["coverage"] = out["covered"] / out["n"] if out["n"] else None
    out["cond_accuracy"] = (out["correct"] / out["covered"]
                            if out["covered"] else None)
    pa, pd = out["pools"]["assert"], out["pools"]["deny"]
    if pa["accuracy"] is not None and pd["accuracy"] is not None:
        out["bias_gap"] = abs(pa["accuracy"] - pd["accuracy"])
    out["latency_mean"] = (out["latency_total"] / out["n"]
                           if out["n"] else None)
    return out


def run_cell(arm, corpus_name):
    facts, meta = load_corpus(corpus_name)
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
    key = f"{arm}:{corpus_name}"
    done = ckpt.get(key, {})
    todo = [(j, job) for j, job in enumerate(jobs) if str(j) not in done]
    print(f"[{key}] {len(jobs)} sentences, {len(todo)} remaining",
          flush=True)
    if todo:
        # construct backends
        if arm in ("A", "S"):
            newsroom.FACTS = [(s, None, None) for (s, _, _) in facts]
            prod_ex = LocalExtractor()
        masks = {}
        if arm == "S":
            raw = json.load(open(MASKS))
            masks = raw.get(corpus_name, {})
        pool_seen = {}
        job_keys = {}
        for j, (i, pool, s) in enumerate(jobs):
            k2 = (i, pool)
            idx = pool_seen.get(k2, 0)
            pool_seen[k2] = idx + 1
            job_keys[j] = f"{i}:{pool}:{idx}"
        if arm == "A":
            def do(sent, jkey):
                t0 = time.time()
                f, st = prod_ex.extract(sent, "stance02")
                return {"fact": f,
                        "stance": ("ABSTAIN" if f < 0 else
                                   "ASSERT" if st else "DENY"),
                        "latency": time.time() - t0}
        elif arm == "B":
            def do(sent, jkey):
                return run_single(
                    arm, facts_block, sent,
                    lambda p: local_chat(p, think=True,
                                         max_tokens=12000))
        elif arm in ("C", "D"):
            think = arm == "D"
            mt = 12000 if think else 256

            def do(sent, jkey):
                return run_structured(
                    arm, facts, facts_block, sent,
                    lambda p: local_chat(p, think=think,
                                         max_tokens=mt))
        elif arm == "S":
            def do(sent, jkey):
                return run_skeleton(
                    facts, facts_block, sent, jkey, masks,
                    lambda p: local_chat(p, max_tokens=64),
                    lambda s2: prod_ex.extract(s2, "stance02-topic"))
        elif arm in ("EA", "EC"):
            if arm == "EA":
                def do(sent, jkey):
                    return run_single(arm, facts_block, sent,
                                      lambda p: hosted_chat(p))
            else:
                def do(sent, jkey):
                    return run_structured(
                        arm, facts, facts_block, sent,
                        lambda p: hosted_chat(p))
        else:
            raise ValueError(arm)
        t0 = time.time()
        for n, (j, (i, pool, sent)) in enumerate(todo):
            try:
                rec = do(sent, job_keys[j])
            except Exception as e:
                rec = {"fact": -1, "stance": "ABSTAIN",
                       "error": f"{type(e).__name__}: {e}",
                       "latency": 0.0}
            rec["gold_fact"] = i
            rec["gold_pool"] = pool
            done[str(j)] = rec
            if (n + 1) % 20 == 0 or n + 1 == len(todo):
                ckpt[key] = done
                json.dump(ckpt, open(CKPT, "w"), indent=1)
                print(f"  {n+1}/{len(todo)} ({time.time()-t0:.0f}s)",
                      flush=True)
        ckpt[key] = done
        json.dump(ckpt, open(CKPT, "w"), indent=1)
    out = score_cell(jobs, done, meta)
    pa, pd = out["pools"]["assert"], out["pools"]["deny"]
    print(f"[{key}] acc={out['accuracy']:.3f} cov={out['coverage']:.3f} "
          f"assert={pa['accuracy']:.3f} deny={pd['accuracy']:.3f} "
          f"gap={out.get('bias_gap', float('nan')):.3f} "
          f"excl={out['excluded']} err={out['errors']}", flush=True)
    results = {}
    if os.path.exists(RESULTS):
        results = json.load(open(RESULTS))
    results[key] = out
    json.dump(results, open(RESULTS, "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True,
                    choices=["A", "B", "C", "D", "S", "EA", "EC"])
    ap.add_argument("--corpus", required=True,
                    choices=["realwire", "realwire_t", "indie",
                             "counterfactual"])
    a = ap.parse_args()
    run_cell(a.arm, a.corpus)
