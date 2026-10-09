"""LORA-01 trainer (frozen design: docs/LORA-01.md).

QLoRA on Qwen/Qwen3.5-9B: NF4 double-quant base, rank 16, alpha 32,
dropout 0.05, language-model linear projections only (vision tower
excluded), cosine schedule, warmup 0.03, effective batch 32
(8 x grad-accum 4), max seq 1024, seed 20261009, BF16 compute,
gradient checkpointing, paged 8-bit AdamW. Loss on the assistant
completion only. LR and epochs are the frozen grid axes (argv).

Usage: lora01_train.py --data lora01_train.jsonl --lr 1e-4
       --epochs 2 --out ~/lora01/adapters/lr1e4-ep2 [--limit N]
"""

import argparse
import json

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from torch.utils.data import Dataset
from transformers import (AutoModelForImageTextToText, AutoTokenizer,
                          BitsAndBytesConfig, Trainer, TrainingArguments)

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

    tok = AutoTokenizer.from_pretrained(MODEL)
    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL, quantization_config=bnb, device_map={"": 0},
        torch_dtype=torch.bfloat16)
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=True)

    import torch.nn as nn
    targets = sorted({
        name for name, mod in model.named_modules()
        if isinstance(mod, nn.Linear) and "language_model" in name
        and "lm_head" not in name})
    print(f"target linear modules: {len(targets)}")
    lcfg = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM", target_modules=targets)
    model = get_peft_model(model, lcfg)
    model.print_trainable_parameters()

    ds = CompletionDataset(args.data, tok, limit=args.limit)
    import math
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
        gradient_checkpointing=True,
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
