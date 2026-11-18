#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"
export PATH="${PYENV_ROOT:-$HOME/.pyenv}/shims:$HOME/.local/bin:$PATH"
uv_bin=$(command -v uv)

extract_dir="data/evaluation/h11-dev-500-confirm-extract"
base_dir="data/evaluation/h11-dev-500-confirm"
h8_dir="data/evaluation/h11-dev-500-confirm-h8"
h9_dir="data/evaluation/h11-dev-500-confirm-h9"
h10_dir="data/evaluation/h11-dev-500-confirm-h10"
extract_file="$extract_dir/extract.jsonl"
candidate_file="$base_dir/candidate-pools.jsonl"

extract_count=$(wc -l < "$extract_file")
if [[ "$extract_count" -ne 500 ]]; then
  printf 'expected 500 extractions, found %s\n' "$extract_count" >&2
  exit 1
fi

printf '%s stage=candidate-pools status=starting\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_e4_experiment.py prepare \
  --extract-file "$extract_file" --out-dir "$base_dir"

printf '%s stage=B4 status=starting\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_e4_experiment.py score \
  --extract-file "$extract_file" --out-dir "$base_dir" --row-limit 500

printf '%s stage=H8 status=starting\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_h7_soft_matching.py score \
  --candidate-file "$candidate_file" --b4-file "$base_dir/reranked.jsonl" \
  --out-dir "$h8_dir" --split dev --fixed-only --row-limit 500
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_h7_soft_matching.py evaluate \
  --candidate-file "$candidate_file" --b4-file "$base_dir/reranked.jsonl" \
  --out-dir "$h8_dir" --split dev --fixed-only

printf '%s stage=H9 status=starting\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_h9_edge_path.py score \
  --candidate-file "$candidate_file" --h8-file "$h8_dir/retrieval.jsonl" \
  --out-dir "$h9_dir" --split dev --row-limit 500
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_h9_edge_path.py evaluate \
  --candidate-file "$candidate_file" --h8-file "$h8_dir/retrieval.jsonl" \
  --out-dir "$h9_dir" --split dev

printf '%s stage=H10 status=starting\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_h10_endpoint_paths.py score \
  --candidate-file "$candidate_file" --h9-file "$h9_dir/retrieval.jsonl" \
  --out-dir "$h10_dir" --split dev --row-limit 500
PYTHONPATH=src:scripts "$uv_bin" run --extra e4 python -u scripts/factkg_h10_endpoint_paths.py evaluate \
  --candidate-file "$candidate_file" --h9-file "$h9_dir/retrieval.jsonl" \
  --out-dir "$h10_dir" --split dev

printf '%s stage=retrieval status=complete summary=%s\n' \
  "$(date --iso-8601=seconds)" "$h10_dir/retrieval-summary.json"
