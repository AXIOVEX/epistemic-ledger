"""STANCE-02 mask construction (dataset building, not a measured arm).

For every sentence in REALWIRE, REALWIRE-T, and COUNTERFACTUAL,
produce a masked variant: the proposition's semantic identity replaced
by [PROPOSITION X], the complete discourse frame preserved verbatim.
Generated with the local model, then human-QC'd (every mask read;
fixes and degenerate marks applied in stance02_masks_qc.py and
recorded in the frozen skeleton_masks.json header).

Checkpointed; reruns resume. Output: skeleton_masks.json
{corpus: {"fact:pool:idx": {"masked": str}}}
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import stance02  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "skeleton_masks.json")
CKPT = os.path.join(HERE, "skeleton_masks_checkpoint.json")

MASK_PROMPT = (
    "Rewrite the sentence below, replacing every part that states "
    "or refers to the specific claim with the placeholder "
    "[PROPOSITION X]. Keep all other words exactly as they are - "
    "especially negations, hedges, quotation marks, and discourse "
    "markers such as 'despite', 'claims that', and 'shown to be "
    "false'. People's names and publication names may stay.\n\n"
    'The claim is: "{stmt}"\n\nSentence: "{sent}"\n\n'
    "Return ONLY the rewritten sentence, nothing else.")


def main():
    all_masks = {}
    if os.path.exists(OUT):
        all_masks = json.load(open(OUT))
    ck = {}
    if os.path.exists(CKPT):
        ck = json.load(open(CKPT))
    for corpus in ("realwire", "realwire_t", "counterfactual"):
        facts, _ = stance02.load_corpus(corpus)
        done = ck.get(corpus, {})
        masks = all_masks.get(corpus, {})
        jobs = []
        for i, (stmt, apool, dpool) in enumerate(facts):
            for pool, pool_items in (("assert", apool), ("deny", dpool)):
                for idx, s in enumerate(pool_items):
                    jobs.append((f"{i}:{pool}:{idx}", stmt, s))
        todo = [j for j in jobs if j[0] not in done]
        print(f"[{corpus}] {len(jobs)} sentences, {len(todo)} to mask",
              flush=True)
        for n, (key, stmt, sent) in enumerate(todo):
            try:
                text, _, _ = stance02.local_chat(
                    MASK_PROMPT.format(stmt=stmt, sent=sent),
                    max_tokens=300)
                masked = text.strip().strip('"')
            except Exception as e:
                masked = f"ERROR: {type(e).__name__}: {e}"
            done[key] = {"masked": masked}
            if (n + 1) % 25 == 0 or n + 1 == len(todo):
                ck[corpus] = done
                json.dump(ck, open(CKPT, "w"), indent=1)
                print(f"  {n+1}/{len(todo)}", flush=True)
        ck[corpus] = done
        masks.update(done)
        all_masks[corpus] = masks
        json.dump(ck, open(CKPT, "w"), indent=1)
        json.dump(all_masks, open(OUT, "w"), indent=1)
    print("MASKS-DONE")


if __name__ == "__main__":
    main()
