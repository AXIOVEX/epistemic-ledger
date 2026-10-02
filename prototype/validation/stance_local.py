"""STANCE-01 Part 1 census runner (protocol frozen in docs/STANCE-01.md).

Three prompt arms x corpora, one run per cell, checkpointed:

  arm A: production LocalExtractor prompt, verbatim.
  arm B: arm A + the frozen stance-lock paragraph (appended to the
         prompt immediately before the JSON instruction).
  arm C: two-pass - pass 1 quotes the operative clause + fact index,
         pass 2 classifies the quote alone against the fact statement.

Arm C pass 1 gets max_tokens=256 (quotes can be long; the production
64-token cap would truncate them into unparseable JSON) - an
implementation parameter, disclosed here; everything else (temperature
0, system prompt, thinking off) matches production.

Scoring mirrors the earlier censuses: a sentence is correct iff the
fact index AND the stance are both right; fact_wrong = wrong index
(or abstention -1); value_wrong = right index, wrong stance; errors
(unparseable / HTTP) count as failures and are never re-asked within
the run. Checkpoints make a crashed cell resumable; completed cells
are final.

Usage: python3 stance_local.py --arm A --corpus realwire
       python3 stance_local.py --arm B --corpus realwire_t
       python3 stance_local.py --arm C --corpus indie
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
RESULTS = os.path.join(HERE, "stance_local_results.json")
CKPT = os.path.join(HERE, "stance_local_checkpoint.json")

STANCE_PARAGRAPH = (
    "Important: report what the SENTENCE claims, not what you know. "
    "A sentence can assert something false, and a sentence can deny "
    "something true. Your own knowledge of these topics must not "
    "influence your answer: if the sentence asserts the fact, answer "
    "says_true=true even when you are certain the fact is false; if "
    "the sentence denies the fact, answer says_true=false even when "
    "you are certain the fact is true.")


def load_corpus(name):
    """Return list of (statement, assert_pool, deny_pool)."""
    if name == "realwire":
        from realwire_corpus import REALWIRE_FACTS
        return [(s, list(a), list(d)) for (s, a, d) in REALWIRE_FACTS]
    if name == "realwire_t":
        from realwire_t_corpus import REALWIRET_FACTS
        return [(f["statement"], list(f["assert"]), list(f["deny"]))
                for f in REALWIRET_FACTS]
    if name == "indie":
        from indie_corpus import INDIE_FACTS
        return [(s, list(a), list(d)) for (s, a, d) in INDIE_FACTS]
    raise ValueError(name)


class ArmBExtractor(LocalExtractor):
    def extract(self, sentence, source):
        body = (sentence.split("] ", 1)[1] if "] " in sentence
                else sentence)
        prompt = (f"Facts:\n{self.facts_block}\n\n"
                  f'Sentence: "{body}"\n\n'
                  "Which fact does the sentence report on, and does it "
                  "assert that fact is TRUE or FALSE? "
                  f"{STANCE_PARAGRAPH} "
                  "Return ONLY JSON: "
                  '{"fact": <index>, "says_true": <true|false>}')
        text = self._complete(prompt)
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0))
        return int(data["fact"]), bool(data["says_true"])


class ArmCExtractor(LocalExtractor):
    def _complete_n(self, prompt, max_tokens):
        body = json.dumps({
            "model": self.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system",
                 "content": "You extract structured data. "
                            "Return only JSON."},
                {"role": "user", "content": prompt}],
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode()
        import urllib.request
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        self.calls += 1
        return data["choices"][0]["message"]["content"]

    def extract(self, sentence, source):
        body = (sentence.split("] ", 1)[1] if "] " in sentence
                else sentence)
        prompt1 = (f"Facts:\n{self.facts_block}\n\n"
                   f'Sentence: "{body}"\n\n'
                   "Quote the exact words in the sentence that state "
                   "its claim about one of these facts. Return ONLY "
                   'JSON: {"fact": <index>, "quote": "<the exact '
                   'words>"}')
        text1 = self._complete_n(prompt1, 256)
        m = re.search(r"\{.*\}", text1, re.S)
        d1 = json.loads(m.group(0))
        fact = int(d1["fact"])
        quote = str(d1["quote"])
        stmt = self.fact_statements[fact]
        prompt2 = (f'A sentence claims: "{quote}"\n\n'
                   f"Fact {fact}: {stmt}\n\n"
                   "Does the quoted text assert that this fact is TRUE "
                   "or FALSE? Return ONLY JSON: "
                   '{"says_true": <true|false>}')
        text2 = self._complete_n(prompt2, 64)
        m2 = re.search(r"\{.*\}", text2, re.S)
        d2 = json.loads(m2.group(0))
        return fact, bool(d2["says_true"])


def make_extractor(arm, facts):
    newsroom.FACTS = [(s, None, None) for (s, _, _) in facts]
    if arm == "A":
        ex = LocalExtractor()
    elif arm == "B":
        ex = ArmBExtractor()
    elif arm == "C":
        ex = ArmCExtractor()
        ex.fact_statements = [s for (s, _, _) in facts]
    else:
        raise ValueError(arm)
    return ex


def run_cell(arm, corpus_name):
    facts = load_corpus(corpus_name)
    jobs = []
    for i, (_, apool, dpool) in enumerate(facts):
        for s in apool:
            jobs.append((i, "assert", s, True))
        for s in dpool:
            jobs.append((i, "deny", s, False))
    ckpt = {}
    if os.path.exists(CKPT):
        ckpt = json.load(open(CKPT))
    key = f"{arm}:{corpus_name}"
    done = ckpt.get(key, {})
    todo = [(j, job) for j, job in enumerate(jobs)
            if str(j) not in done]
    print(f"[{key}] {len(jobs)} sentences, {len(todo)} remaining",
          flush=True)
    if todo:
        ex = make_extractor(arm, facts)
        t0 = time.time()
        for n, (j, (i, pool, sent, want)) in enumerate(todo):
            try:
                got_fact, got_true = ex.extract(sent, "stance-census")
                rec = {"fact": i, "pool": pool, "got_fact": got_fact,
                       "got_true": got_true}
            except Exception as e:  # recorded, never retried this run
                rec = {"fact": i, "pool": pool,
                       "error": f"{type(e).__name__}: {e}"}
            done[str(j)] = rec
            if (n + 1) % 25 == 0 or n + 1 == len(todo):
                ckpt[key] = done
                json.dump(ckpt, open(CKPT, "w"), indent=1)
                print(f"  {n+1}/{len(todo)} "
                      f"({time.time()-t0:.0f}s)", flush=True)
        ckpt[key] = done
        json.dump(ckpt, open(CKPT, "w"), indent=1)
    # score the cell
    out = {"correct": 0, "fact_wrong": 0, "value_wrong": 0, "errors": 0,
           "n": len(jobs), "pools": {}, "per_fact": {}}
    for pool in ("assert", "deny"):
        out["pools"][pool] = {"correct": 0, "fact_wrong": 0,
                              "value_wrong": 0, "errors": 0,
                              "n": sum(1 for j in jobs if j[1] == pool)}
    for i in range(len(facts)):
        out["per_fact"][str(i)] = {
            "correct": 0, "fact_wrong": 0, "value_wrong": 0,
            "errors": 0, "n": sum(1 for j in jobs if j[0] == i)}
    for j, (i, pool, sent, want) in enumerate(jobs):
        rec = done[str(j)]
        if "error" in rec:
            kind = "errors"
        elif rec["got_fact"] != i:
            kind = "fact_wrong"
        elif rec["got_true"] != want:
            kind = "value_wrong"
        else:
            kind = "correct"
        out[kind] += 1
        out["pools"][pool][kind] += 1
        out["per_fact"][str(i)][kind] += 1
    acc = {pool: (p["correct"] / p["n"] if p["n"] else None)
           for pool, p in out["pools"].items()}
    print(f"[{key}] correct {out['correct']}/{out['n']} "
          f"acc={out['correct']/out['n']:.3f} pools={acc}", flush=True)
    results = {}
    if os.path.exists(RESULTS):
        results = json.load(open(RESULTS))
    results[key] = out
    json.dump(results, open(RESULTS, "w"), indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True, choices="ABC")
    ap.add_argument("--corpus", required=True,
                    choices=["realwire", "realwire_t", "indie"])
    a = ap.parse_args()
    run_cell(a.arm, a.corpus)
