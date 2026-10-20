"""LORA-01 dev-set census + grid selection (frozen design: docs/LORA-01.md).

Runs the production extraction prompt (Arm A protocol) over the DEV
corpus (lora01_dev.json, 12 propositions x 12 sentences) in-process
for each grid adapter, plus the un-adapted base for reference. Dev is
used ONLY for grid selection; no held-out or REALWIRE-family contact.

Selection rule (frozen): highest dev balanced accuracy (mean of
assert-pool and deny-pool accuracy); ties broken by lower learning
rate, then fewer epochs. Parse failures and no-match answers count
as not-correct (coverage reported alongside).

In-process measurement is deliberate for selection: no quantization
or serving confound between cells. The selected adapter is later
merged, quantized, and measured served (see docs/LORA-01.md).

Usage: lora01_devcensus.py [--cells lr1e4-ep2,lr1e4-ep3,...]
Output: lora01_dev_results.json next to this file.
"""

import unsloth  # noqa: F401  (must precede transformers/peft imports)
import argparse
import gc
import json
import re
import sys
from pathlib import Path

import torch
from unsloth import FastVisionModel

sys.path.insert(0, str(Path(__file__).parent))

MODEL = "Qwen/Qwen3.5-9B"
SYSTEM = "You extract structured data. Return only JSON."
PROMPT_TAIL = (
    "\n\nWhich fact does the sentence report on, and does it assert "
    "that fact is TRUE or FALSE? Return ONLY JSON: "
    '{"fact": <index>, "says_true": <true|false>}')

CELL_META = {  # name -> (lr, epochs) for the frozen tie-break order
    "lr1e4-ep2": (1e-4, 2),
    "lr1e4-ep3": (1e-4, 3),
    "lr2e4-ep2": (2e-4, 2),
    "lr2e4-ep3": (2e-4, 3),
}


def facts_block(statements):
    return "\n".join(f"{i}. {s}" for i, s in enumerate(statements))


def parse_json(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def run_cell(name, model_path, facts, items, tok):
    model, proc = FastVisionModel.from_pretrained(
        model_name=model_path, load_in_4bit=True, max_seq_length=1024)
    tok = proc.tokenizer
    FastVisionModel.for_inference(model)
    block = facts_block([f["statement"] for f in facts])
    pools = {"assert": [0, 0], "deny": [0, 0]}  # correct, total
    abstain = 0
    records = []
    for (fi, pool, sent) in items:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user",
                 "content": f"Facts:\n{block}\n\nSentence: \"{sent}\""
                            + PROMPT_TAIL}]
        prompt = tok.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True,
            enable_thinking=False)
        ids = tok(prompt, return_tensors="pt",
                  add_special_tokens=False).to("cuda")
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=32,
                                 do_sample=False,
                                 pad_token_id=tok.pad_token_id)
        text = tok.decode(out[0][ids["input_ids"].shape[1]:],
                          skip_special_tokens=True)
        got = parse_json(text)
        want_true = (pool == "assert")
        ok = (got is not None and got.get("fact") == fi
              and got.get("says_true") == want_true)
        if got is None or got.get("fact", -1) < 0:
            abstain += 1
        pools[pool][1] += 1
        pools[pool][0] += 1 if ok else 0
        records.append({"fact": fi, "pool": pool, "ok": bool(ok),
                        "raw": text.strip()[:120]})
    del model, proc
    gc.collect()
    torch.cuda.empty_cache()
    a = pools["assert"][0] / pools["assert"][1]
    d = pools["deny"][0] / pools["deny"][1]
    return {"assert_acc": a, "deny_acc": d,
            "balanced_acc": (a + d) / 2,
            "total_acc": (pools["assert"][0] + pools["deny"][0])
                         / (pools["assert"][1] + pools["deny"][1]),
            "abstentions": abstain, "n": len(items),
            "records": records}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells", default=",".join(CELL_META))
    ap.add_argument("--include-base", action="store_true")
    args = ap.parse_args()
    here = Path(__file__).parent
    dev = json.loads((here / "lora01_dev.json").read_text())
    facts = dev["facts"]
    items = []
    for fi, f in enumerate(facts):
        for s in f["assert"]:
            items.append((fi, "assert", s))
        for s in f["deny"]:
            items.append((fi, "deny", s))
    results = {}
    names = (["base"] if args.include_base else []) \
        + args.cells.split(",")
    for name in names:
        path = MODEL if name == "base" else str(
            Path.home() / "lora01" / "adapters" / name)
        print(f"=== cell {name} ({path}) ===", flush=True)
        results[name] = run_cell(name, path, facts, items, None)
        r = results[name]
        print(f"  assert {r['assert_acc']:.3f} deny {r['deny_acc']:.3f} "
              f"balanced {r['balanced_acc']:.3f} total {r['total_acc']:.3f} "
              f"abstain {r['abstentions']}", flush=True)
    cells = {k: v for k, v in results.items() if k in CELL_META}
    winner = sorted(
        cells.items(),
        key=lambda kv: (-kv[1]["balanced_acc"], CELL_META[kv[0]][0],
                        CELL_META[kv[0]][1]))[0][0]
    results["selection"] = {"winner": winner,
                            "rule": "max balanced_acc; ties: lower lr, "
                                    "then fewer epochs"}
    (here / "lora01_dev_results.json").write_text(
        json.dumps(results, indent=1))
    print("WINNER:", winner)


if __name__ == "__main__":
    main()
