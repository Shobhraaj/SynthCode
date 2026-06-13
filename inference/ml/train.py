from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,31}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a lightweight token-based baseline model.")
    parser.add_argument("--input", required=True, help="Path to labeled JSONL data.")
    parser.add_argument("--output", required=True, help="Path to write model JSON.")
    parser.add_argument("--min-token-count", type=int, default=3, help="Minimum token frequency to keep.")
    return parser.parse_args()


def iter_rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            label = int(row.get("label", 0))
            text = str(row.get("content") or row.get("text") or "")
            if text:
                yield text, 1 if label > 0 else 0


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def train_model(rows, min_token_count: int) -> dict:
    ai_docs = 0
    human_docs = 0
    ai_counts: Counter[str] = Counter()
    human_counts: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()

    for text, label in rows:
        tokens = tokenize(text)
        if not tokens:
            continue
        token_counts.update(tokens)
        if label == 1:
            ai_docs += 1
            ai_counts.update(tokens)
        else:
            human_docs += 1
            human_counts.update(tokens)

    vocab = [token for token, count in token_counts.items() if count >= min_token_count]
    if not vocab:
        raise SystemExit("No tokens available after filtering; check dataset and min-token-count.")

    ai_total = sum(ai_counts[token] for token in vocab)
    human_total = sum(human_counts[token] for token in vocab)
    vocab_size = len(vocab)

    weights = {}
    for token in vocab:
        p_token_ai = (ai_counts[token] + 1.0) / (ai_total + vocab_size)
        p_token_human = (human_counts[token] + 1.0) / (human_total + vocab_size)
        weights[token] = round(math.log(p_token_ai / p_token_human), 6)

    ai_prior = (ai_docs + 1.0) / (ai_docs + human_docs + 2.0)
    intercept = round(math.log(ai_prior / (1.0 - ai_prior)), 6)
    return {
        "model_type": "token_log_odds_baseline",
        "intercept": intercept,
        "weights": weights,
        "meta": {
            "ai_docs": ai_docs,
            "human_docs": human_docs,
            "vocab_size": vocab_size,
        },
    }


def main():
    args = parse_args()
    input_path = Path(args.input)
    model = train_model(iter_rows(input_path), min_token_count=args.min_token_count)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    print(f"Saved baseline model to {output_path} with {model['meta']['vocab_size']} tokens")


if __name__ == "__main__":
    main()
