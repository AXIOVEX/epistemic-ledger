"""Corpus validation for the consolidation pass (CONSOLIDATION-01).

Hand-written claims with planted relationships; the LLM sees text only
(all credences 0.5). Measures proposition-understanding precision/recall
for CONTRADICTS and SAME — the two relations heuristics cannot do.

Ground truth:
  SAME groups: G1 (bridge toll, 3 phrasings), G2 (CEO, 2), G3 (referendum, 2)
  CONTRADICTS: 5 pairs (same subject, incompatible content)
  Traps (NOT contradictions): AND/OR-compatible pair; weaker/stronger
  compatible pair; same-subject unrelated pair; unrelated fillers.

Usage: python corpus.py [model ...]   (default: Sonnet 4.5 + Haiku 4.5)
Spend is capped by the client's $5 budget; actual cost is printed.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from ledger import Ledger  # noqa: E402
import consolidation  # noqa: E402

CLAIMS = [
    # G1 paraphrases
    "The Harlow Bridge toll is $5.",
    "Drivers pay five dollars to cross the Harlow Bridge.",
    "Crossing Harlow Bridge costs $5.",
    # G2 paraphrases
    "Maria Chen is the CEO of AstraCorp.",
    "AstraCorp's chief executive is Maria Chen.",
    # G3 paraphrases
    "The Meridian referendum passed.",
    "Voters approved the Meridian referendum.",
    # C1
    "The Kestrel pipeline began operations in March.",
    "The Kestrel pipeline remains shut down and has never operated.",
    # C2
    "Copper trades above $5 per pound.",
    "Copper trades below $4 per pound.",
    # C3
    "Vantia's parliament was dissolved by the president.",
    "Vantia's parliament is in session and was never dissolved.",
    # C4
    "The Solstice probe landed intact on Mars.",
    "The Solstice probe burned up in the Martian atmosphere and never reached the surface.",
    # C5
    "QuantumLeap split its stock 2-for-1.",
    "QuantumLeap has never split its stock.",
    # T1 AND/OR trap (compatible)
    "Both the toll increase and the tax cut took effect.",
    "At least one of the toll increase and the tax cut took effect.",
    # T3 weaker/stronger trap (compatible)
    "At least 100 people attended the rally.",
    "More than 50 people attended the rally.",
    # T2/T4 unrelated same-subject
    "The Falcons won the championship.",
    "The Falcons' stadium is being renovated.",
    "Dr. Thorne won the Novum Prize.",
    "Dr. Thorne's lab published a paper on enzymes.",
    # fillers
    "The city library extended its opening hours.",
    "The reservoir is at 80% capacity.",
]

SAME_GROUPS = [{0, 1, 2}, {3, 4}, {5, 6}]
CONTRADICTS = {(7, 8), (9, 10), (11, 12), (13, 14), (15, 16)}


def pairs_of(groups):
    out = set()
    for g in groups:
        for a in g:
            for b in g:
                if a < b:
                    out.add((a, b))
    return out


def score(found, truth):
    tp = len(found & truth)
    fp = len(found - truth)
    fn = len(truth - found)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    return prec, rec, tp, fp, fn


def run_model(model, cap=5.00):
    d = tempfile.mkdtemp(prefix="corpus-")
    L = Ledger(d)
    ids = [L.assert_claim(s, 0.5) for s in CLAIMS]
    idx = {cid: i for i, cid in enumerate(ids)}
    client = consolidation.OpenRouterClient(model=model, cap_usd=cap)
    rep = consolidation.Consolidator(L, client).run()

    found_contra = set()
    for e in L.open_contradictions():
        a, b = idx[e["payload"]["claim_a"]], idx[e["payload"]["claim_b"]]
        found_contra.add((min(a, b), max(a, b)))
    topics = {}
    for cid, topic in rep["topics_assigned"].items():
        topics.setdefault(topic, set()).add(idx[cid])
    found_same = pairs_of(topics.values())

    truth_same = pairs_of(SAME_GROUPS)
    cp = score(found_contra, CONTRADICTS)
    sp = score(found_same, truth_same)
    print(f"\n== {model} ==  cost=${client.spent:.4f} calls={client.calls}")
    print(f"CONTRADICTS: P={cp[0]:.2f} R={cp[1]:.2f} "
          f"(tp={cp[2]} fp={cp[3]} fn={cp[4]})")
    if found_contra - CONTRADICTS:
        for a, b in sorted(found_contra - CONTRADICTS):
            print(f"  FP: [{a}] {CLAIMS[a][:50]}  vs  [{b}] {CLAIMS[b][:50]}")
    if CONTRADICTS - found_contra:
        for a, b in sorted(CONTRADICTS - found_contra):
            print(f"  FN: [{a}] {CLAIMS[a][:50]}  vs  [{b}] {CLAIMS[b][:50]}")
    print(f"SAME:        P={sp[0]:.2f} R={sp[1]:.2f} "
          f"(tp={sp[2]} fp={sp[3]} fn={sp[4]})")
    if found_same - truth_same:
        for a, b in sorted(found_same - truth_same):
            print(f"  FP: [{a}] {CLAIMS[a][:50]}  vs  [{b}] {CLAIMS[b][:50]}")
    print(f"supports proposed (not scored): {len(rep['supports_proposed'])}")
    shutil.rmtree(d)
    return client.spent


if __name__ == "__main__":
    models = sys.argv[1:] or ["anthropic/claude-sonnet-4.5",
                              "anthropic/claude-haiku-4.5"]
    total = 0.0
    for m in models:
        total += run_model(m)
    print(f"\ntotal spend: ${total:.4f}")
