from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split JSONL dataset into train/valid/test sets.")
    parser.add_argument("--input", required=True, help="Source JSONL dataset")
    parser.add_argument("--output-dir", required=True, help="Directory for split files")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--valid-ratio", type=float, default=0.1)
    parser.add_argument("--test-ratio", type=float, default=0.1)
    return parser.parse_args()


def main():
    args = parse_args()
    rows = [line.strip() for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("No rows found in input dataset.")
    random.Random(args.seed).shuffle(rows)

    total = len(rows)
    valid_count = int(total * args.valid_ratio)
    test_count = int(total * args.test_ratio)
    train_count = total - valid_count - test_count

    splits = {
        "train.jsonl": rows[:train_count],
        "valid.jsonl": rows[train_count : train_count + valid_count],
        "test.jsonl": rows[train_count + valid_count :],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, split_rows in splits.items():
        (output_dir / name).write_text("\n".join(split_rows) + ("\n" if split_rows else ""), encoding="utf-8")

    print(json.dumps({"total": total, "train": train_count, "valid": valid_count, "test": test_count}, indent=2))


if __name__ == "__main__":
    main()
