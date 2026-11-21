#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

candidate_file="data/evaluation/h8-dev-500/candidate-pools.jsonl"
prepare_unit="soft-isomorphism-h8-prepare.service"

while systemctl --user is-active --quiet "$prepare_unit"; do
  count=$(wc -l < "$candidate_file")
  printf '%s candidate_pools=%s/500 prepare=active\n' "$(date --iso-8601=seconds)" "$count"
  sleep 60
done

count=$(wc -l < "$candidate_file")
if [[ "$count" -ne 500 ]]; then
  printf '%s candidate_pools=%s/500 prepare=failed\n' "$(date --iso-8601=seconds)" "$count"
  exit 1
fi

printf '%s candidate_pools=500/500 scoring=B4\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts uv run --extra e4 python -u scripts/factkg_e4_experiment.py score \
  --extract-file data/evaluation/h8-dev-500-extract/extract.jsonl \
  --out-dir data/evaluation/h8-dev-500 --row-limit 500

printf '%s scoring=H8\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts uv run --extra e4 python -u scripts/factkg_h7_soft_matching.py score \
  --candidate-file "$candidate_file" \
  --b4-file data/evaluation/h8-dev-500/reranked.jsonl \
  --out-dir data/evaluation/h8-dev-500-c7 --split dev --fixed-only --row-limit 500

printf '%s evaluating=retrieval\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts python -u scripts/factkg_h7_soft_matching.py evaluate \
  --candidate-file "$candidate_file" \
  --b4-file data/evaluation/h8-dev-500/reranked.jsonl \
  --out-dir data/evaluation/h8-dev-500-c7 --split dev --fixed-only

printf '%s evaluating=reader\n' "$(date --iso-8601=seconds)"
PYTHONPATH=src:scripts python -u scripts/factkg_h7_soft_matching.py read \
  --candidate-file "$candidate_file" \
  --b4-file data/evaluation/h8-dev-500/reranked.jsonl \
  --out-dir data/evaluation/h8-dev-500-c7 --split dev --fixed-only --include-b1 \
  --kilo-auth-provider itmo_lab

printf '%s complete\n' "$(date --iso-8601=seconds)"
