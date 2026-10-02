"""Newsroom experiment: integrated adversarial validation (NEWSROOM-01).

A simulated newsroom exercises the full v0.6 feature set TOGETHER against
one thesis: a ledger-backed memory beats frozen memory on a realistic,
adversarial, multi-source belief stream.

World: 12 binary facts (fictional news) that flip over time. Six sources
with trust tiers report in natural-language sentences (template registry;
see the Extractor note below):
  wire-a, wire-b (contributor, honest, ~0.9 accurate)
  blog-c, blog-d (provisional, honest, ~0.73 accurate)
  rumor-e, rumor-f (unregistered, ADVERSARIAL: lie ~2/3 of the time)

Agent design:
- One claim per ordinary fact (F0-F9). Reports update Bayesian posterior
  odds with the source's *learned* accuracy as the likelihood; the ledger
  stores the trajectory bitemporally and propagates to derived combos.
  (The accumulation math lives in the agent; the ledger is the memory,
  not the inference engine. Both agents share it — the ONLY difference
  under test is revision vs. frozen.)
- Contested facts F10/F11 get per-desk assessment claims (wire-desk /
  rumor-desk) with D-S intervals -> the genuine contradictions for the
  detection measurement.
- Derived: D1=AND(F1,F2), D2=OR(F1,F2) [same parents: the spurious-probe
  pair], D3=AND(F3,F4,F5), D4=OR(F6,F7).
- Trust learning: reports are verified against ground truth with a
  10-step delay ("eventual ground truth"); per-source accuracy is
  Laplace-smoothed toward the tier prior. A known liar's reports get
  INVERTED by the odds update — the correct Bayesian response.
- Detection runs at steps 10/20/30. Genuine desk contradictions are
  auto-resolved (rumor desk should lose on entrenchment); spurious
  AND/OR flags are left open and COUNTED, not resolved — blind
  auto-resolution of heuristic flags would corrupt the accuracy metric,
  which is itself a finding.
- Outcomes recorded at steps 20/40/60 -> learn_entrenchment (Brier path).

Baseline (naive): identical report processing, trust learning, and
posteriors; derived claims frozen at step 5; no detection.

Extractor note: ModeledExtractor maps the template registry to
(fact, value) with tiered misparse noise. The NL layer is theater for
the template registry — this experiment tests belief-structure dynamics
(adversarial sources, trust, revision, detection), NOT NLP. LLMExtractor
is the interface-ready swap for real parsing (needs approved API spend).

Metric: per-step quiz accuracy (facts + desk views + derived) vs.
ground truth, ledger vs. naive, 5 seeds. Plus detection precision/
recall and kill metrics.
"""

import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ledger import Ledger  # noqa: E402

# ----------------------------------------------------------------------
# world: facts + NL templates
# ----------------------------------------------------------------------

FACTS = [
    ("AstraCorp's CEO is Maria Chen",
     ["AstraCorp named Maria Chen as chief executive.",
      "Maria Chen took over as CEO of AstraCorp."],
     ["AstraCorp denied that Maria Chen is its CEO.",
      "Maria Chen is not the CEO of AstraCorp, the company said."]),
    ("The Harlow Bridge toll is $5",
     ["The Harlow Bridge toll is $5.",
      "Drivers pay $5 to cross Harlow Bridge."],
     ["The Harlow Bridge toll is not $5.",
      "Harlow Bridge crossings cost $3, not $5."]),
    ("Team Falcons won the championship",
     ["Team Falcons won the championship.",
      "The Falcons are champions after last night's final."],
     ["Team Falcons lost the championship final.",
      "The championship went to the Wolves, not the Falcons."]),
    ("The Meridian referendum passed",
     ["The Meridian referendum passed.",
      "Voters approved the Meridian referendum."],
     ["The Meridian referendum failed.",
      "The Meridian referendum did not pass."]),
    ("QuantumLeap's stock split 2-for-1",
     ["QuantumLeap split its stock 2-for-1.",
      "QuantumLeap shares split two-for-one."],
     ["QuantumLeap did not split its stock.",
      "No QuantumLeap stock split occurred."]),
    ("Dr. Aris Thorne won the Novum Prize",
     ["Dr. Aris Thorne won the Novum Prize.",
      "The Novum Prize went to Dr. Aris Thorne."],
     ["Dr. Aris Thorne did not win the Novum Prize.",
      "The Novum Prize went to someone else, not Thorne."]),
    ("The Kestrel pipeline is operational",
     ["The Kestrel pipeline is operational.",
      "Kestrel pipeline operations began today."],
     ["The Kestrel pipeline is still offline.",
      "Kestrel pipeline operations have not started."]),
    ("Vantia's parliament dissolved",
     ["Vantia's parliament was dissolved.",
      "The president dissolved Vantia's parliament."],
     ["Vantia's parliament remains in session.",
      "Reports of Vantia's parliament dissolving are false."]),
    ("The Solstice probe landed on Mars",
     ["The Solstice probe landed on Mars.",
      "Solstice touched down on the Martian surface."],
     ["The Solstice probe missed Mars.",
      "Solstice failed to land on Mars."]),
    ("Copper prices hit $5/lb",
     ["Copper hit $5 per pound.",
      "Copper prices reached $5/lb."],
     ["Copper remains below $5 per pound.",
      "Copper did not reach $5/lb."]),
    ("The Aldane dam will be decommissioned",
     ["The Aldane dam will be decommissioned.",
      "Decommissioning of the Aldane dam was approved."],
     ["The Aldane dam will remain in service.",
      "Plans to decommission the Aldane dam were scrapped."]),
    ("Northwind Airlines is merging with Skylink",
     ["Northwind Airlines is merging with Skylink.",
      "Northwind and Skylink announced a merger."],
     ["Northwind denied merger talks with Skylink.",
      "No Northwind-Skylink merger is happening."]),
]

N_FACTS = len(FACTS)
CONTESTED = (10, 11)  # per-desk assessment claims, not merged facts

SOURCES = [
    # (name, tier, true_accuracy, adversarial)
    ("wire-a", "contributor", 0.90, False),
    ("wire-b", "contributor", 0.88, False),
    ("blog-c", "provisional", 0.75, False),
    ("blog-d", "provisional", 0.72, False),
    ("rumor-e", None, 0.30, True),
    ("rumor-f", None, 0.35, True),
]
TIER_PRIOR = {"contributor": 0.85, "provisional": 0.70, None: 0.60}
PARSE_ACC = {"contributor": 0.95, "provisional": 0.90, None: 0.85}


class Extractor:
    def extract(self, sentence, source):
        raise NotImplementedError


class ModeledExtractor(Extractor):
    """Template registry + tiered misparse noise. Stands in for NLP."""

    def __init__(self, rng):
        self.rng = rng
        self.registry = {}
        for i, (_, trues, falses) in enumerate(FACTS):
            for s in trues:
                self.registry[s] = (i, True)
            for s in falses:
                self.registry[s] = (i, False)

    def extract(self, sentence, source):
        body = sentence.split("] ", 1)[1]
        fact_id, value = self.registry[body]
        tier = next(t for n, t, _, _ in SOURCES if n == source)
        if self.rng.random() > PARSE_ACC[tier]:
            value = not value  # misparse
        return fact_id, value


class LLMExtractor(Extractor):
    """Real NL parsing via an LLM (OpenRouter), one call per report.

    Extraction is a cheap task: default model gpt-4o-mini. The prompt
    lists the 12 fact statements; the model returns the fact index and
    whether the sentence asserts it true or false."""

    def __init__(self, model="openai/gpt-4o-mini", cap_usd=5.00):
        import consolidation
        self.client = consolidation.OpenRouterClient(model=model,
                                                     cap_usd=cap_usd)
        self.facts_block = "\n".join(
            f"{i}. {s}" for i, (s, _, _) in enumerate(FACTS))

    def extract(self, sentence, source):
        import json as _json
        import re as _re
        body = sentence.split("] ", 1)[1] if "] " in sentence else sentence
        prompt = (f"Facts:\n{self.facts_block}\n\n"
                  f'Sentence: "{body}"\n\n'
                  "Which fact does the sentence report on, and does it "
                  "assert that fact is TRUE or FALSE? Return ONLY JSON: "
                  '{"fact": <index>, "says_true": <true|false>}')
        text, _ = self.client.complete(
            prompt, system="You extract structured data. "
                           "Return only JSON.")
        m = _re.search(r"\{.*\}", text, _re.S)
        data = _json.loads(m.group(0))
        return int(data["fact"]), bool(data["says_true"])


class LocalExtractor(Extractor):
    """NL parsing via a LOCAL OpenAI-compatible endpoint (llama.cpp
    server, default Qwen3-8B on the owner's desktop). Same prompt and
    parsing as LLMExtractor so results are comparable; the claim being
    measured is different — whether a free local model extracts well
    enough for the ledger's end-to-end advantage to survive. No API
    spend; calls counted, failures raise (never silently misparsed).
    Qwen3 thinking is disabled via chat_template_kwargs."""

    def __init__(self, base_url="http://localhost:8083/v1",
                 model="qwen3-8b-local", timeout=120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.calls = 0
        self.facts_block = "\n".join(
            f"{i}. {s}" for i, (s, _, _) in enumerate(FACTS))

    def _complete(self, prompt):
        import json as _json
        import urllib.request
        body = _json.dumps({
            "model": self.model,
            "temperature": 0,
            "max_tokens": 64,
            "messages": [
                {"role": "system",
                 "content": "You extract structured data. "
                            "Return only JSON."},
                {"role": "user", "content": prompt}],
            "chat_template_kwargs": {"enable_thinking": False},
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = _json.loads(r.read())
        self.calls += 1
        return data["choices"][0]["message"]["content"]

    def extract(self, sentence, source):
        import json as _json
        import re as _re
        body = sentence.split("] ", 1)[1] if "] " in sentence else sentence
        prompt = (f"Facts:\n{self.facts_block}\n\n"
                  f'Sentence: "{body}"\n\n'
                  "Which fact does the sentence report on, and does it "
                  "assert that fact is TRUE or FALSE? Return ONLY JSON: "
                  '{"fact": <index>, "says_true": <true|false>}')
        text = self._complete(prompt)
        m = _re.search(r"\{.*\}", text, _re.S)
        data = _json.loads(m.group(0))
        return int(data["fact"]), bool(data["says_true"])


def bayes_update(prior, says_true, acc, temper=1.0):
    """Posterior after one report. temper < 1 tempers the report's
    log-likelihood ratio (lam ** temper): the calibration lever for
    the agent's measured overconfidence (NEWSROOM-01: accurate but
    overconfident posteriors; CALIBRATION-01). temper=1.0 is the
    original update, exactly."""
    prior = min(0.99, max(0.01, prior))
    lam = acc / (1 - acc) if says_true else (1 - acc) / acc
    odds = prior / (1 - prior) * lam ** temper
    return odds / (1 + odds)


# ----------------------------------------------------------------------
# agents
# ----------------------------------------------------------------------

class NewsroomAgent:
    """Ledger-backed newsroom memory."""

    def __init__(self, rng, extractor=None, temper=1.0):
        self.rng = rng
        self.temper = temper
        self.dropped_extractions = 0
        self.dir = tempfile.mkdtemp(prefix="newsroom-")
        self.L = Ledger(self.dir)
        self.extractor = extractor if extractor is not None \
            else ModeledExtractor(rng)
        for name, tier, _, _ in SOURCES:
            if tier:
                self.L.register_writer(name, tier)
        self.L.register_writer("wire-desk", "contributor")
        self.L.register_writer("rumor-desk", "provisional")
        self.facts = {}
        for i, (stmt, _, _) in enumerate(FACTS):
            if i in CONTESTED:
                continue
            self.facts[i] = self.L.assert_claim(f"news: {stmt}", 0.5)
        self.desks = {}
        for i in CONTESTED:
            stmt = FACTS[i][0]
            self.desks[(i, "wire")] = self.L.assert_claim(
                f"wire-desk assessment: {stmt}", 0.5, writer="wire-desk")
            self.desks[(i, "rumor")] = self.L.assert_claim(
                f"rumor-desk assessment: {stmt}", 0.5, writer="rumor-desk")
        self.derived = {}
        combos = [("D1", "noisy-and", [1, 2]), ("D2", "noisy-or", [1, 2]),
                  ("D3", "noisy-and", [3, 4, 5]), ("D4", "noisy-or", [6, 7])]
        for name, kind, parents in combos:
            joiner = " AND " if kind == "noisy-and" else " OR "
            stmt = joiner.join(FACTS[p][0] for p in parents)
            did = self.L.assert_claim(f"derived {name}: {stmt}", 0.5)
            for p in parents:
                self.L.add_support(did, self.facts[p], "evidential")
            self.L.set_combo(did, kind)
            self.derived[name] = (did, kind, parents)
        # trust learning state
        self.acc = {n: TIER_PRIOR[t] for n, t, _, _ in SOURCES}
        self._ver_correct = {n: 0 for n, _, _, _ in SOURCES}
        self._ver_total = {n: 0 for n, _, _, _ in SOURCES}
        self.pending = []  # (source, fact, says_true, step)
        self.detect_stats = {"genuine": 0, "genuine_opps": 0,
                             "spurious": 0, "other": 0}

    def _set(self, cid, score):
        if abs(score - self.L.get_score(cid)) < 1e-12:
            return
        self.L._set_score(cid, score, None, actor="agent")
        self.L._revisit(cid, {cid: score}, actor="agent")

    def _desk_update_interval(self, cid):
        s = self.L.get_score(cid)
        self.L.set_interval(cid, max(0.0, s - 0.05), min(1.0, s + 0.05),
                            actor="agent")

    def ingest(self, sentence, source, step):
        fact_id, says_true = self.extractor.extract(sentence, source)
        self.ingest_extracted(fact_id, says_true, source, step)

    def ingest_extracted(self, fact_id, says_true, source, step):
        """Update from an already-extracted report. The trial extracts
        once and feeds both agents identically (shared extraction:
        otherwise the two agents misparse the same sentence differently,
        confounding the comparison).

        An extraction that names no known fact (e.g. the local
        extractor's emergent -1 abstention on off-topic text,
        FREETEXT-01) is dropped and counted, never ingested: there
        is no claim it could honestly update."""
        if (not isinstance(fact_id, int) or isinstance(fact_id, bool)
                or not 0 <= fact_id < N_FACTS):
            self.dropped_extractions += 1
            return
        acc = self.acc[source]
        desk = None
        if fact_id in CONTESTED:
            tier = next(t for n, t, _, _ in SOURCES if n == source)
            desk = "wire" if tier else "rumor"
            cid = self.desks[(fact_id, desk)]
        else:
            cid = self.facts[fact_id]
        new = bayes_update(self.L.get_score(cid), says_true, acc,
                           temper=self.temper)
        self._set(cid, new)
        if desk:
            self._desk_update_interval(cid)
        self.pending.append((source, fact_id, says_true, step))

    def verify_trust(self, step, truth_history, delay=10):
        """Score pending reports against eventual ground truth; accumulate
        per-source verification counts (Laplace-smoothed toward tier prior)."""
        still = []
        for source, fact, says_true, t0 in self.pending:
            if t0 > step - delay:
                still.append((source, fact, says_true, t0))
                continue
            self._ver_total[source] += 1
            if says_true == truth_history[t0][fact]:
                self._ver_correct[source] += 1
        self.pending = still
        for n, tier, _, _ in SOURCES:
            tot = self._ver_total[n]
            if tot:
                self.acc[n] = ((10 * TIER_PRIOR[tier] + self._ver_correct[n]) /
                               (10 + tot))

    def detect_and_resolve(self):
        """Run detection; auto-resolve ONLY genuine desk contradictions.
        Spurious flags are counted, not resolved (finding, not a bug).

        The topic filter models what a real deployment gets from its NL
        pipeline (proposition identity); here the agent supplies it from
        its own claim registry. Without it, interval-conflict flags any
        opposed decided pair (measured cross-fact false positives)."""
        topic = {(cid): ("fact", fact_i)
                 for (fact_i, _), cid in self.desks.items()}
        for cid in self.L.detect_contradictions(topic_of=topic.get):
            self.detect_stats["genuine_opps"] += 0  # counted below
            opened = [e for e in self.L.open_contradictions()
                      if e["event_id"] == cid]
            if not opened:
                continue  # held by governance gate
            pl = opened[0]["payload"]
            a, b = pl["claim_a"], pl["claim_b"]
            desk_ids = set(self.desks.values())
            d1, d2 = self.derived["D1"][0], self.derived["D2"][0]
            if {a, b} <= desk_ids and pl.get("signal", "").startswith(
                    "interval-conflict"):
                # genuine: the two desks of one contested fact
                fa = next(k for k, v in self.desks.items() if v == a)
                fb = next(k for k, v in self.desks.items() if v == b)
                if fa[0] == fb[0] and fa[1] != fb[1]:
                    self.detect_stats["genuine"] += 1
                    self.L.resolve_contradiction(cid, actor="agent")
                    continue
            if {a, b} == {d1, d2}:
                self.detect_stats["spurious"] += 1
                continue
            self.detect_stats["other"] += 1

    def answer_fact(self, i):
        if i in CONTESTED:
            return self.L.get_score(self.desks[(i, "wire")]) > 0.5
        return self.L.get_score(self.facts[i]) > 0.5

    def answer_derived(self, name):
        did, kind, parents = self.derived[name]
        return self.L.get_score(did) > 0.5

    def close(self):
        shutil.rmtree(self.dir)


class NaiveNewsroom(NewsroomAgent):
    """Frozen baseline: identical processing, derived frozen at step 5."""

    def __init__(self, rng, extractor=None, temper=1.0):
        super().__init__(rng, extractor=extractor, temper=temper)
        self.frozen_derived = None

    def freeze(self):
        self.frozen_derived = {
            n: self.L.get_score(did) > 0.5
            for n, (did, _, _) in self.derived.items()}

    def answer_derived(self, name):
        return self.frozen_derived[name]


# ----------------------------------------------------------------------
# run
# ----------------------------------------------------------------------

def run_trial(seed, steps=60, flip_p=0.04, extractor_factory=None,
              temper=1.0):
    rng = random.Random(seed)
    truth = [{i: rng.random() < 0.5 for i in range(N_FACTS)}]
    shared_ext = extractor_factory(rng) if extractor_factory else None
    agent = NewsroomAgent(rng, extractor=shared_ext, temper=temper)
    naive = NaiveNewsroom(rng, extractor=shared_ext, temper=temper)
    truth_history = [dict(truth[0])]
    # initial report sweep so both agents start informed (shared extraction)
    for i in range(N_FACTS):
        for name, _, acc, _ in SOURCES[:2]:
            says = truth[0][i] if rng.random() < acc else not truth[0][i]
            sent = rng.choice(FACTS[i][1 if says else 2])
            fact_id, extracted = agent.extractor.extract(
                f"[{name}] {sent}", name)
            agent.ingest_extracted(fact_id, extracted, name, 0)
            naive.ingest_extracted(fact_id, extracted, name, 0)
    naive.freeze()  # step-0 values; re-frozen at step 5 per design

    ledger_err = naive_err = quizzes = 0
    ledger_derived_err = naive_derived_err = derived_quizzes = 0

    def quiz(step_truth):
        nonlocal ledger_err, naive_err, quizzes
        nonlocal ledger_derived_err, naive_derived_err, derived_quizzes
        for i in range(N_FACTS):
            t = step_truth[i]
            quizzes += 1
            ledger_err += agent.answer_fact(i) != t
            naive_err += naive.answer_fact(i) != t
        for name, (did, kind, parents) in agent.derived.items():
            vals = [step_truth[p] for p in parents]
            t = all(vals) if kind == "noisy-and" else any(vals)
            quizzes += 1
            derived_quizzes += 1
            ledger_err += agent.answer_derived(name) != t
            naive_err += naive.answer_derived(name) != t
            ledger_derived_err += agent.answer_derived(name) != t
            naive_derived_err += naive.answer_derived(name) != t

    for step in range(1, steps + 1):
        cur = dict(truth_history[-1])
        for i in cur:
            if rng.random() < flip_p:
                cur[i] = not cur[i]
        truth_history.append(cur)
        # each source reports on 2 random facts (shared extraction)
        for name, _, acc, _ in SOURCES:
            for i in rng.sample(range(N_FACTS), 2):
                says = cur[i] if rng.random() < acc else not cur[i]
                sent = rng.choice(FACTS[i][1 if says else 2])
                fact_id, extracted = agent.extractor.extract(
                    f"[{name}] {sent}", name)
                agent.ingest_extracted(fact_id, extracted, name, step)
                naive.ingest_extracted(fact_id, extracted, name, step)
        # hot contested streams: wire-a and rumor-e report on F10/F11
        # every step, so the desk-contradiction window is measurable
        for i in CONTESTED:
            for name, _, acc, _ in (SOURCES[0], SOURCES[4]):
                says = cur[i] if rng.random() < acc else not cur[i]
                sent = rng.choice(FACTS[i][1 if says else 2])
                fact_id, extracted = agent.extractor.extract(
                    f"[{name}] {sent}", name)
                agent.ingest_extracted(fact_id, extracted, name, step)
                naive.ingest_extracted(fact_id, extracted, name, step)
        agent.verify_trust(step, truth_history)
        naive.verify_trust(step, truth_history)
        if step == 5:
            naive.freeze()
        if step in (5, 10, 15, 20, 25, 30):
            agent.detect_and_resolve()
        if step in (20, 40, 60):
            for i in range(N_FACTS):
                cid = (agent.desks[(i, "wire")] if i in CONTESTED
                       else agent.facts[i])
                agent.L.record_outcome(cid, int(cur[i]))
        quiz(cur)

    rep = agent.L.learn_entrenchment()
    km = agent.L.kill_metrics()
    bars = agent.L.check_kill_bars()
    stats = dict(agent.detect_stats)
    accs = dict(agent.acc)
    agent.close()
    naive.close()
    return (ledger_err / quizzes, naive_err / quizzes, quizzes,
            ledger_derived_err / derived_quizzes,
            naive_derived_err / derived_quizzes,
            stats, accs,
            {"brier_learned": len(rep), "brier": km["brier"],
             "dropped_extractions": agent.dropped_extractions,
             "kill_ok": bars["ok"],
             "breached": [b["criterion"] for b in bars["breached"]],
             "n_open_contra": km["n_open_contradictions"]})


if __name__ == "__main__":
    print("seed | ledger_err naive_err | genuine spurious other | "
          "rumor acc learned")
    ls, ns, lds, nds = [], [], [], []
    all_stats = {"genuine": 0, "spurious": 0, "other": 0}
    for seed in range(5):
        le, ne, q, lde, nde, stats, accs, meta = run_trial(seed)
        ls.append(le)
        ns.append(ne)
        lds.append(lde)
        nds.append(nde)
        for k in all_stats:
            all_stats[k] += stats[k]
        print(f"{seed} | {le:.3f} {ne:.3f} (derived {lde:.3f} {nde:.3f}) | "
              f"{stats['genuine']} {stats['spurious']} {stats['other']} | "
              f"rumor-e {accs['rumor-e']:.2f} rumor-f {accs['rumor-f']:.2f} "
              f"wire-a {accs['wire-a']:.2f} | kill_ok={meta['kill_ok']} "
              f"breached={meta['breached']}")
    l, n = sum(ls) / 5, sum(ns) / 5
    ld, nd = sum(lds) / 5, sum(nds) / 5
    print(f"\n[{q} quizzes] mean ledger_err={l:.3f} mean naive_err={n:.3f}")
    print(f"staleness reduction = {n - l:.3f} "
          f"({(n - l) / n * 100:.1f}% of naive errors eliminated)")
    print(f"[derived only] ledger={ld:.3f} naive={nd:.3f} "
          f"reduction={nd - ld:.3f} ({(nd - ld) / nd * 100:.1f}%)")
    print(f"detection totals: genuine={all_stats['genuine']} "
          f"spurious(D1/D2)={all_stats['spurious']} other={all_stats['other']}")
