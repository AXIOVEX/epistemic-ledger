"""LORA-01 winner merge (frozen design fallback, docs/LORA-01.md).

The primary serving form (adapter GGUF from convert_lora_to_gguf.py
on the unchanged Q4_K_M base) is unattainable for this model:
conversion raises NotImplementedError ("can't reshape the row size
trivially") on the fused linear-attention LoRA tensors, for adapters
from both trainer implementations. The design's named fallback
applies: merge the adapter into the base weights and quantize the
merged model to Q4_K_M GGUF, served standalone. Recorded as a
deviation in the execution record: quantization noise applies to
base+delta jointly rather than to the base alone.

Usage: lora01_merge.py --adapter ~/lora01/adapters/<cell>
       --out ~/lora01/merged/<cell>
Prints the produced GGUF path and its sha256.
"""

import unsloth  # noqa: F401  (must precede transformers/peft imports)
import argparse
import hashlib
from pathlib import Path

from unsloth import FastVisionModel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    model, proc = FastVisionModel.from_pretrained(
        model_name=args.adapter, load_in_4bit=True,
        max_seq_length=1024)
    model.save_pretrained_gguf(args.out, proc,
                               quantization_method="q4_k_m")
    ggufs = sorted(Path(args.out).rglob("*.gguf"))
    for g in ggufs:
        h = hashlib.sha256(g.read_bytes()).hexdigest()
        print("GGUF", g, g.stat().st_size, h)
    print("MERGE-DONE")


if __name__ == "__main__":
    main()
