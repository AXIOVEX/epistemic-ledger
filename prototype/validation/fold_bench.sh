#!/usr/bin/env bash
# MODEL-FOLD bench: run the STANCE-02 census protocol (Arm A baseline +
# Arm C structured, frozen prompts/scoring) against alternative local
# models, on the desktop's FREE GPU, without touching the STANCE-02
# server (port 8083) or its frozen result files.
#
# Method: copy prototype/validation to ~/modelfold, point the copy's
# LOCAL_URL at a bench server on port 8084 (alias kept as
# "qwen3-8b-local", the name local_chat sends), then for each model:
# start server -> run cells -> rename results to fold_results_<label>.json.
# Incumbent comparison: Qwen3-8B's STANCE-02 Phase-1 cells (same protocol,
# same config family: ctx 8192, parallel 4, temperature 0).
set -u
SRC="$HOME/epistemic-ledger/prototype"
ROOT="$HOME/modelfold"
WORK="$ROOT/prototype/validation"
LOG="$ROOT/fold_bench.log"
mkdir -p "$ROOT"
exec >>"$LOG" 2>&1
echo "=== fold bench started $(date -Is) ==="

if [ ! -f "$WORK/stance02.py" ]; then
  cp -r "$SRC" "$ROOT/"
  # point the COPY at the bench port; the frozen original is untouched
  sed -i 's/8083/8084/' "$WORK/stance02.py"
  echo "workdir copied; LOCAL_URL lines now:"
  grep -n "8084" "$WORK/stance02.py" | head -3
fi
cd "$WORK"

source "$HOME/llama.cpp-release/env.sh"

run_model () {
  label="$1"; model="$2"
  echo "--- model $label ($model) $(date -Is)"
  rm -f stance02_results.json stance02_checkpoint.json
  CUDA_VISIBLE_DEVICES=0 nohup "$LLAMA_SERVER" \
    -m "$model" --port 8084 --ctx-size 8192 --parallel 4 \
    -ngl 99 --alias qwen3-8b-local \
    > "$HOME/models/llama-server-8084.log" 2>&1 &
  srv=$!
  ok=0
  for i in $(seq 1 30); do
    sleep 3
    if curl -fsS http://localhost:8084/v1/models >/dev/null 2>&1; then
      ok=1; break
    fi
  done
  if [ "$ok" != "1" ]; then
    echo "SERVER-FAILED $label"; tail -5 "$HOME/models/llama-server-8084.log"
    kill "$srv" 2>/dev/null; return
  fi
  echo "server up pid=$srv"
  for arm in A C; do
    for corpus in realwire realwire_t indie; do
      echo "cell $label $arm:$corpus $(date -Is)"
      timeout 3600 python3 -u stance02.py --arm "$arm" --corpus "$corpus"
    done
  done
  [ -f stance02_results.json ] && \
    mv stance02_results.json "fold_results_$label.json"
  [ -f stance02_checkpoint.json ] && \
    mv stance02_checkpoint.json "fold_checkpoint_$label.json"
  kill "$srv" 2>/dev/null
  sleep 3
  echo "--- model $label done $(date -Is)"
}

run_model qwen35-9b  "$HOME/models/Qwen3.5-9B-Q4_K_M.gguf"
run_model llama31-8b "$HOME/models/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf"
run_model mistral-7b "$HOME/models/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"
run_model gemma2-9b  "$HOME/models/gemma-2-9b-it-Q4_K_M.gguf"
echo "=== fold bench complete $(date -Is) ==="
