#!/usr/bin/env bash
# Run a small E0 (policy adherence) per candidate chat model, sequentially, writing report/results/model_compare/.
# Usage: scripts/compare_models_e0.sh <n_cases> <model> [<model> ...]
set -u
N=$1; shift
cd "$(dirname "$0")/../experiments"
mkdir -p ../report/results/model_compare
for m in "$@"; do
  tag=$(echo "$m" | tr '/.' '__')
  echo "=== $m ($(date +%T))"
  CHAT_MODEL=$m E0_NAME=model_compare/e0_$tag MLFLOW_DISABLE_AGENT_HINT=1 uv run python -W ignore e0_policy.py "$N" > ../report/results/model_compare/e0_$tag.log 2>&1
  echo "=== done $m exit=$? ($(date +%T))"
done
