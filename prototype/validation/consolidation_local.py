"""Local consolidation validation (LOCAL-CONSOLIDATION-01).

The consolidation pass (Design Memo 08) was validated on OpenRouter
models only (CONSOLIDATION-01: Sonnet 4.5 and Haiku 4.5, both perfect
on the corpus; Haiku matched Sonnet in the head-to-head at ~1/3 the
cost). This runs the SAME two validations with the pass ported to a
free local model — Qwen3-8B via llama.cpp on the owner's desktop —
through consolidation.LocalClient, a drop-in for OpenRouterClient.

Two arms, kept strictly separate in the results:
  default        — the protocol as CONSOLIDATION-01 ran it
                   (temperature 0, no repetition penalty).
  repeat_penalty — a diagnostic arm: identical prompts, identical
                   everything, except the local client's decoding
                   uses llama.cpp's classic repeat_penalty=1.1. It
                   exists because the default arm's head-to-head
                   reply degenerated into a repetition loop; whether
                   standard anti-repetition decoding restores the
                   pass is deployment knowledge for the port, NOT a
                   rescue of the default arm's numbers.

Writes consolidation_local_results.json next to this script.
Run unbuffered (python3 -u) on the desktop (llama.cpp on :8083).
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


def run_arm(name, **client_kw):
    arm = {}
    client = consolidation.LocalClient(**client_kw)
    t0 = time.time()
    arm["corpus"] = corpus.run_model("qwen3-8b-local (llama.cpp)",
                                     client=client)
    arm["corpus"]["seconds"] = round(time.time() - t0, 1)
    print(f"[{name}] corpus done in {arm['corpus']['seconds']}s",
          flush=True)
    client2 = consolidation.LocalClient(**client_kw)
    t0 = time.time()
    try:
        arm["head_to_head"] = head_to_head.main(client=client2)
    except Exception as e:  # a failed pass is a result, not a crash
        arm["head_to_head"] = {"error": f"{type(e).__name__}: {e}"}
        print(f"[{name}] head-to-head C pass failed: {e}", flush=True)
    arm["head_to_head_seconds"] = round(time.time() - t0, 1)
    print(f"[{name}] head-to-head done in "
          f"{arm['head_to_head_seconds']}s", flush=True)
    return arm


ARMS = {
    "default": {},
    "repeat_penalty_1_1": {"repeat_penalty": 1.1},
    # diagnostic: is the failure a reasoning failure? Qwen3's
    # template default (thinking on), generous token budget, served
    # at a larger per-slot context (see LOCAL-CONSOLIDATION-01).
    "thinking": {"thinking": True, "max_tokens": 6000},
}


def main():
    wanted = sys.argv[1:] or list(ARMS)
    out = {}
    if os.path.exists(RESULTS):
        with open(RESULTS) as f:
            out = json.load(f)
    for name in wanted:
        out[name] = run_arm(name, **ARMS[name])
    with open(RESULTS, "w") as f:
        json.dump(out, f, indent=1)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
