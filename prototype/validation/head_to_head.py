"""Head-to-head: heuristic vs heuristic+topic vs LLM consolidation
(CONSOLIDATION-01).

Builds one newsroom ledger (12 steps, no detection during the run, so
the state is pristine), snapshots desk scores, then runs three
detectors on three identical copies:

  A: heuristic detect_contradictions() unfiltered
  B: heuristic + topic filter (agent-supplied topics)
  C: LLM consolidation pass (statements + credences only)

Ground truth: the two contested-fact desk pairs (wire-desk vs
rumor-desk on F10/F11) — scored as genuine only if the desks are
actually opposed at snapshot. Traps: the (D1,D2) AND/OR pair and any
cross-fact pair.

Usage: python head_to_head.py [model]   (default Haiku 4.5)
"""

import os
import random
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger import Ledger  # noqa: E402
import consolidation  # noqa: E402
from newsroom import NewsroomAgent, FACTS, N_FACTS, SOURCES, CONTESTED  # noqa: E402


def build_agent(seed=0, steps=12):
    rng = random.Random(seed)
    truth = [{i: rng.random() < 0.5 for i in range(N_FACTS)}]
    agent = NewsroomAgent(rng)
    truth_history = [dict(truth[0])]
    for i in range(N_FACTS):
        for name, _, acc, _ in SOURCES[:2]:
            says = truth[0][i] if rng.random() < acc else not truth[0][i]
            sent = rng.choice(FACTS[i][1 if says else 2])
            fid, ext = agent.extractor.extract(f"[{name}] {sent}", name)
            agent.ingest_extracted(fid, ext, name, 0)
    for step in range(1, steps + 1):
        cur = dict(truth_history[-1])
        for i in cur:
            if rng.random() < 0.04:
                cur[i] = not cur[i]
        truth_history.append(cur)
        for name, _, acc, _ in SOURCES:
            for i in rng.sample(range(N_FACTS), 2):
                says = cur[i] if rng.random() < acc else not cur[i]
                sent = rng.choice(FACTS[i][1 if says else 2])
                fid, ext = agent.extractor.extract(f"[{name}] {sent}", name)
                agent.ingest_extracted(fid, ext, name, step)
        for i in CONTESTED:
            for name, _, acc, _ in (SOURCES[0], SOURCES[4]):
                says = cur[i] if rng.random() < acc else not cur[i]
                sent = rng.choice(FACTS[i][1 if says else 2])
                fid, ext = agent.extractor.extract(f"[{name}] {sent}", name)
                agent.ingest_extracted(fid, ext, name, step)
        agent.verify_trust(step, truth_history)
    return agent


def declared_pairs(L):
    out = set()
    for e in L.open_contradictions():
        a, b = e["payload"]["claim_a"], e["payload"]["claim_b"]
        out.add(frozenset((a, b)))
    return out


def main(client=None):
    model = sys.argv[1] if len(sys.argv) > 1 else "anthropic/claude-haiku-4.5"
    agent = build_agent()

    label = {}
    for i, cid in agent.facts.items():
        label[cid] = f"F{i}"
    for (i, desk), cid in agent.desks.items():
        label[cid] = f"F{i}-{desk}"
    for name, (did, _, _) in agent.derived.items():
        label[did] = name

    desk_pairs = {}
    opposed = {}
    for i in CONTESTED:
        w = agent.desks[(i, "wire")]
        r = agent.desks[(i, "rumor")]
        desk_pairs[i] = frozenset((w, r))
        sw, sr = agent.L.get_score(w), agent.L.get_score(r)
        opposed[i] = (sw - 0.5) * (sr - 0.5) < 0 and min(
            abs(sw - 0.5), abs(sr - 0.5)) > 0.2
        print(f"F{i} desks at snapshot: wire={sw:.2f} rumor={sr:.2f} "
              f"opposed={opposed[i]}")
    d1d2 = frozenset((agent.derived["D1"][0], agent.derived["D2"][0]))
    genuine = {p for i, p in desk_pairs.items() if opposed[i]}

    copies = {}
    for tag in "ABC":
        dest = tempfile.mkdtemp(prefix=f"h2h-{tag}-")
        shutil.rmtree(dest)
        shutil.copytree(agent.dir, dest)
        copies[tag] = Ledger(dest)

    results = {}

    def report(tag, pairs):
        tp = len(pairs & genuine)
        trap = 1 if d1d2 in pairs else 0
        other_fp = len(pairs - genuine - {d1d2})
        names = sorted("=".join(sorted(label[c] for c in p)) for p in pairs)
        print(f"{tag}: genuine {tp}/{len(genuine)}  AND/OR-trap {trap}  "
              f"other-FP {other_fp}   pairs: {names}")
        results[tag] = {"genuine": tp, "genuine_total": len(genuine),
                        "trap": trap, "other_fp": other_fp,
                        "pairs": names}

    # A: heuristic unfiltered
    LA = copies["A"]
    LA.detect_contradictions()
    print("\nA: heuristic, unfiltered")
    report("A", declared_pairs(LA))

    # B: heuristic + topics
    LB = copies["B"]
    topic = {cid: ("fact", i) for (i, _), cid in agent.desks.items()}
    LB.detect_contradictions(topic_of=topic.get)
    print("B: heuristic + topic filter")
    report("B", declared_pairs(LB))

    # C: LLM consolidation
    LC = copies["C"]
    if client is None:
        client = consolidation.OpenRouterClient(model=model, cap_usd=5.00)
    label_model = getattr(client, "model", model)
    rep = consolidation.Consolidator(LC, client).run()
    print(f"C: LLM consolidation ({label_model})  cost=${client.spent:.4f}")
    report("C", declared_pairs(LC))
    print(f"   topics assigned by LLM: {len(rep['topics_assigned'])} claims "
          f"in {len(set(rep['topics_assigned'].values()))} groups; "
          f"supports proposed: {len(rep['supports_proposed'])}")
    # do the LLM topics group the desk pairs together?
    desk_topics = {}
    for i in CONTESTED:
        w, r = agent.desks[(i, "wire")], agent.desks[(i, "rumor")]
        tw, tr = LC.get_topic(w), LC.get_topic(r)
        print(f"   F{i} desk topics: wire={tw} rumor={tr} "
              f"same={tw is not None and tw == tr}")
        desk_topics[f"F{i}"] = (tw is not None and tw == tr)

    agent.close()
    results["C"].update({
        "model": label_model, "calls": client.calls,
        "topics_assigned": len(rep["topics_assigned"]),
        "topic_groups": len(set(rep["topics_assigned"].values())),
        "supports_proposed": len(rep["supports_proposed"]),
        "desk_topics_grouped": desk_topics})
    return results


if __name__ == "__main__":
    main()
