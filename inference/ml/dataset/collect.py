from __future__ import annotations

import argparse
import json
from pathlib import Path

LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect local labeled code files into JSONL.")
    parser.add_argument("--source-dir", required=True, help="Directory with code files.")
    parser.add_argument("--label", required=True, type=int, choices=[0, 1], help="0=human, 1=AI")
    parser.add_argument("--output", required=True, help="Output JSONL path.")
    parser.add_argument("--max-bytes", type=int, default=120_000)
    return parser.parse_args()


def main():
    args = parse_args()
    source_dir = Path(args.source_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with output_path.open("a", encoding="utf-8") as out:
        for path in source_dir.rglob("*"):
            if not path.is_file():
                continue
            language = LANGUAGE_BY_EXTENSION.get(path.suffix.lower())
            if not language:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore")
            if not content.strip() or len(content.encode("utf-8")) > args.max_bytes:
                continue
            row = {
                "path": str(path),
                "language": language,
                "label": args.label,
                "content": content,
            }
            out.write(json.dumps(row) + "\n")
            written += 1
    print(f"Wrote {written} records to {output_path}")


if __name__ == "__main__":
    main()
