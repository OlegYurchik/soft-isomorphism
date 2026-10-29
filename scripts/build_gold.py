"""Build data/evaluation/gold.jsonl from GTSQA and FactKG via the data adapter.

Usage:
    uv run python scripts/build_gold.py [--report]

Options:
    --report   Print coverage summary instead of writing the file.

Output:
    data/evaluation/gold.jsonl  — one JSON object per line, not committed.

Audit rules: docs/annotation-rules.md
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from soft_isomorphism.data.adapter import load_factkg, load_gtsqa
from soft_isomorphism.data.schema import Example, Split

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
OUT_FILE = DATA_DIR / "evaluation" / "gold.jsonl"


def _audit_status(ex: Example) -> tuple[str, str | None]:
    """Return (status, note) for an example per annotation-rules.md §4-5."""
    if not ex.gold_edges:
        return "excluded", "empty_gold"
    if not ex.text.strip():
        return "excluded", "empty_text"

    gi = ex.metadata.get("graph_isomorphism")
    if gi is None:
        return "excluded", "null_type"

    # FactKG Existence with ≤1 edge: thin_gold
    if ex.metadata.get("type") == "Existence" and len(ex.gold_edges) <= 1:
        return "thin_gold", "single_edge_existence"

    return "evaluable", None


def _example_to_record(ex: Example) -> dict:
    status, note = _audit_status(ex)
    return {
        "id": ex.id,
        "source": ex.source.value,
        "split": ex.split.value,
        "text": ex.text,
        "gold_edges": [asdict(e) for e in ex.gold_edges],
        "metadata": ex.metadata,
        "audit_status": status,
        "audit_note": note,
    }


def build(report_only: bool = False) -> None:
    records: list[dict] = []
    stats: dict[str, dict[str, int]] = {}

    datasets = [
        ("GTSQA test", lambda: load_gtsqa(DATA_DIR / "gtsqa", Split.TEST)),
        ("GTSQA train-dev", lambda: load_gtsqa(DATA_DIR / "gtsqa", Split.TRAIN_DEV)),
        ("FactKG dev", lambda: load_factkg(DATA_DIR / "factkg", Split.DEV)),
    ]

    for label, loader in datasets:
        try:
            examples = loader()
        except FileNotFoundError as exc:
            log.warning("Skipping %s: %s", label, exc)
            continue

        ds_stats: dict[str, int] = {}
        for ex in examples:
            rec = _example_to_record(ex)
            records.append(rec)
            ds_stats[rec["audit_status"]] = ds_stats.get(rec["audit_status"], 0) + 1

        stats[label] = ds_stats
        log.info(
            "%s: total=%d  evaluable=%d  excluded=%d  thin_gold=%d  unknown=%d",
            label,
            len(examples),
            ds_stats.get("evaluable", 0),
            ds_stats.get("excluded", 0),
            ds_stats.get("thin_gold", 0),
            ds_stats.get("unknown", 0),
        )

    if not records:
        log.error("No records produced — have you downloaded the datasets?")
        sys.exit(1)

    if report_only:
        _print_report(stats)
        return

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    evaluable = sum(s.get("evaluable", 0) + s.get("thin_gold", 0) for s in stats.values())
    excluded = sum(s.get("excluded", 0) for s in stats.values())
    log.info(
        "Wrote %d records to %s  (evaluable=%d, excluded=%d)",
        len(records),
        OUT_FILE,
        evaluable,
        excluded,
    )
    _print_report(stats)


def _print_report(stats: dict[str, dict[str, int]]) -> None:
    print("\n=== Gold coverage report ===")
    cols = ("Dataset", "Total", "Evaluable", "ThinGold", "Unknown", "Excluded")
    header = f"{cols[0]:<20} {cols[1]:>7} {cols[2]:>10} {cols[3]:>9} {cols[4]:>8} {cols[5]:>9}"
    print(header)
    print("-" * len(header))
    for label, s in stats.items():
        total = sum(s.values())
        print(
            f"{label:<20} {total:>7} {s.get('evaluable', 0):>10} "
            f"{s.get('thin_gold', 0):>9} {s.get('unknown', 0):>8} "
            f"{s.get('excluded', 0):>9}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="Print coverage report only")
    args = parser.parse_args()
    build(report_only=args.report)
