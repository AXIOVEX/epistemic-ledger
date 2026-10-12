"""LORA-01 trainer, Unsloth implementation (frozen design: docs/LORA-01.md).

Implementation deviation record: the original HF/transformers trainer
(lora01_train.py) is pathologically slow for Qwen3.5's hybrid
linear-attention stack on both desktop GPUs (profiled: Ampere-era
CUTLASS BF16 GEMMs at ~1.7 s/call on the Blackwell 5060 Ti; 4070 SUPER
smoke took 5,721 s for 6 optimizer steps) and its adapter then failed
convert_lora_to_gguf.py (NotImplementedError: can't reshape the row
size trivially). This implementation keeps every frozen protocol
parameter identical -- QLoRA NF4 double-quant, rank 16, alpha 32,
dropout 0.05, language-model layers only (vision tower frozen and
untargeted), effective batch 32 (8 x grad-accum 4), max seq 1024,
seed 20261009, cosine schedule, warmup ratio 0.03 (as steps),
paged 8-bit AdamW, completion-only loss on byte-identical prompts --
and changes only the kernel/training implementation to Unsloth's
patched stack. Tokenization and label masking reuse the exact code
path of lora01_train.py.

Usage: lora01_train_unsloth.py --data lora01_train.jsonl --lr 1e-4
       --epochs 2 --out ~/lora01/adapters/lr1e4-ep2 [--limit N]
       [--steps N]
"""

import argparse
import json
import math

import torch
from torch.utils.data import Dataset
from transformers import Trainer, TrainingArguments
from unsloth import FastVisionModel

MODEL = "Qwen/Qwen3.5-9B"


class CompletionDataset(Dataset):
    def __init__(self, path, tok, limit=None, max_len=1024):
        self.rows = []
        skipped = 0
        with open(path) as f:
            lines = [json.loads(x) for x in f]
        if limit:
            lines = lines[:limit]
        for ex in lines:
            msgs = [{"role": "system", "content": ex["system"]},
                    {"role": "user", "content": ex["user"]}]
            prompt = tok.apply_chat_template(
                msgs, tokenize=False, add_generation_prompt=True,
                enable_thinking=False)
            full = prompt + ex["assistant"] + "<|im_end|>"
            p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
            f_ids = tok(full, add_special_tokens=False)["input_ids"]
            if len(f_ids) > max_len:
                skipped += 1
                continue
            labels = [-100] * len(p_ids) + f_ids[len(p_ids):]
            self.rows.append({"input_ids": f_ids, "labels": labels})
        print(f"dataset: {len(self.rows)} examples, {skipped} over-length")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


class Collator:
    def __init__(self, pad_id):
        self.pad_id = pad_id

    def __call__(self, batch):
        maxlen = max(len(b["input_ids"]) for b in batch)
        input_ids, labels, attn = [], [], []
        for b in batch:
            n = len(b["input_ids"])
            pad = maxlen - n
            input_ids.append(b["input_ids"] + [self.pad_id] * pad)
            labels.append(b["labels"] + [-100] * pad)
            attn.append([1] * n + [0] * pad)
        return {"input_ids": torch.tensor(input_ids),
                "labels": torch.tensor(labels),
                "attention_mask": torch.tensor(attn)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--lr", type=float, required=True)
    ap.add_argument("--epochs", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--steps", type=int, default=None)
    args = ap.parse_args()

    model, tok = FastVisionModel.from_pretrained(
        MODEL, load_in_4bit=True, max_seq_length=1024)
    model = FastVisionModel.get_peft_model(
        model,
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=20261009)
    FastVisionModel.for_training(model)
    model.print_trainable_parameters()

    ds = CompletionDataset(args.data, tok, limit=args.limit)
    steps_per_epoch = math.ceil(len(ds) / 32)
    total_steps = (args.steps if args.steps
                   else int(steps_per_epoch * args.epochs))
    warmup_steps = max(1, round(0.03 * total_steps))
    print(f"total steps {total_steps}, warmup steps {warmup_steps}")
    targs = TrainingArguments(
        output_dir=args.out + "-trainer",
        per_device_train_batch_size=8,
        gradient_accumulation_steps=4,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        max_steps=args.steps if args.steps else -1,
        lr_scheduler_type="cosine",
        warmup_steps=warmup_steps,
        logging_steps=5,
        save_strategy="no",
        bf16=True,
        optim="paged_adamw_8bit",
        seed=20261009,
        report_to=[],
    )
    trainer = Trainer(model=model, args=targs, train_dataset=ds,
                      data_collator=Collator(tok.pad_token_id))
    trainer.train()
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    print("ADAPTER-SAVED", args.out)


if __name__ == "__main__":
    main()
