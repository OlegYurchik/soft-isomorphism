#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

candidate_file="data/evaluation/h8-dev-500/candidate-pools.jsonl"
h9_file="data/evaluation/h9-dev-500-diagnostic/retrieval.jsonl"
out_dir="data/evaluation/h10-dev-500-diagnostic"

for required_file in "$candidate_file" "$h9_file" "$out_dir/retrieval.jsonl"; do
  if [[ ! -s "$required_file" ]]; then
    printf 'missing required input: %s\n' "$required_file" >&2
    exit 1
  fi
done

printf '%s reader=H9,H10 model=iairlab/qwen3.8-27b status=starting\n' \
  "$(date --iso-8601=seconds)"

# The Python runner appends one complete claim at a time and validates the
# model and evidence hashes before reusing it, so rerunning this command is
# safe after a gateway failure.
PYTHONPATH=src:scripts uv run python -u scripts/factkg_h10_endpoint_paths.py read \
  --candidate-file "$candidate_file" \
  --h9-file "$h9_file" \
  --out-dir "$out_dir" \
  --split dev \
  --model iairlab/qwen3.8-27b \
  --kilo-auth-provider itmo_lab

printf '%s reader=H9,H10 status=complete summary=%s\n' \
  "$(date --iso-8601=seconds)" "$out_dir/reader-summary.json"
