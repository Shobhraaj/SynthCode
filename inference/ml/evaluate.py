from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,31}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the baseline model on labeled JSONL data.")
    parser.add_argument("--model", required=True, help="Path to model JSON created by train.py")
    parser.add_argument("--input", required=True, help="Path to evaluation JSONL dataset")
    parser.add_argument("--threshold", type=float, default=0.5, help="Decision threshold for class metrics")
    return parser.parse_args()


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def predict_score(model: dict, text: str) -> float:
    token_weights = model.get("weights", {})
    value = float(model.get("intercept", 0.0))
    for token in tokenize(text):
        value += float(token_weights.get(token, 0.0))
    return sigmoid(max(-25.0, min(25.0, value)))


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


def roc_auc(y_true: list[int], y_prob: list[float]) -> float:
    pos = sum(y_true)
    neg = len(y_true) - pos
    if pos == 0 or neg == 0:
        return 0.0
    ranked = sorted(zip(y_prob, y_true), key=lambda item: item[0])
    rank_sum = 0.0
    for index, (_, label) in enumerate(ranked, start=1):
        if label == 1:
            rank_sum += index
    return round((rank_sum - (pos * (pos + 1) / 2)) / (pos * neg), 4)


def main():
    args = parse_args()
    model = json.loads(Path(args.model).read_text(encoding="utf-8"))

    y_true: list[int] = []
    y_pred: list[int] = []
    y_prob: list[float] = []

    for text, label in iter_rows(Path(args.input)):
        prob = predict_score(model, text)
        pred = 1 if prob >= args.threshold else 0
        y_true.append(label)
        y_prob.append(prob)
        y_pred.append(pred)

    if not y_true:
        raise SystemExit("No labeled samples found.")

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(y_true)
    brier = sum((prob - label) ** 2 for prob, label in zip(y_prob, y_true)) / len(y_true)

    metrics = {
        "samples": len(y_true),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) else 0.0,
        "roc_auc": roc_auc(y_true, y_prob),
        "brier": round(brier, 4),
        "threshold": args.threshold,
    }
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
