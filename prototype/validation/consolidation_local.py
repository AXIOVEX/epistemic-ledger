"""Local consolidation validation (LOCAL-CONSOLIDATION-01).

The consolidation pass (Design Memo 08) was validated on OpenRouter
models only (CONSOLIDATION-01: Sonnet 4.5 and Haiku 4.5, both perfect
on the corpus; Haiku matched Sonnet in the head-to-head at ~1/3 the
cost). This runs the SAME two validations with the pass ported to a
free local model — Qwen3-8B via llama.cpp on the owner's desktop —
through consolidation.LocalClient, a drop-in for OpenRouterClient.

  1. Corpus: 27 hand-written claims, planted contradicts/same/traps;
     precision/recall for CONTRADICTS and SAME.
  2. Head-to-head: heuristic vs heuristic+topic-filter vs LLM
     consolidation on identical newsroom ledgers.

Writes consolidation_local_results.json next to this script.
Run unbuffered (python3 -u) on the desktop (needs the llama.cpp
server on :8083).
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consolidation  # noqa: E402
import corpus  # noqa: E402
import head_to_head  # noqa: E402

RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "consolidation_local_results.json")


def main():
    out = {}
    client = consolidation.LocalClient()
    t0 = time.time()
    out["corpus"] = corpus.run_model("qwen3-8b-local (llama.cpp)",
                                     client=client)
    out["corpus"]["seconds"] = round(time.time() - t0, 1)
    print(f"corpus done in {out['corpus']['seconds']}s", flush=True)

    client2 = consolidation.LocalClient()
    t0 = time.time()
    out["head_to_head"] = head_to_head.main(client=client2)
    out["head_to_head_seconds"] = round(time.time() - t0, 1)
    print(f"head-to-head done in {out['head_to_head_seconds']}s",
          flush=True)

    with open(RESULTS, "w") as f:
        json.dump(out, f, indent=1)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
