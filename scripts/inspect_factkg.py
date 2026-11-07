"""Inspect method-safe FactKG records from a trusted upstream checkout."""

import argparse
import json
from dataclasses import asdict

from soft_isomorphism.data.adapter import load_factkg_records
from soft_isomorphism.data.schema import Split


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", help="Directory containing data/factkg_unzip")
    parser.add_argument("--split", choices=("train", "dev", "test"), default="dev")
    args = parser.parse_args()
    inputs, evaluation = load_factkg_records(args.data_dir, Split(args.split))
    print(json.dumps({"count": len(inputs), "input": asdict(inputs[0])}, ensure_ascii=False))
    print(f"evaluator records: {len(evaluation)}; stored separately from method input")


if __name__ == "__main__":
    main()
