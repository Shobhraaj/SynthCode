from __future__ import annotations

import re


class CodePreprocessor:
    MAX_TOKENS = 512
    OVERLAP = 64

    def process_file(self, content: str, language: str, label: int | None = None) -> list[dict]:
        normalized = re.sub(r"\s+", " ", content).strip()
        tokens = normalized.split()
        if not tokens:
            return []
        stride = max(1, self.MAX_TOKENS - self.OVERLAP)
        chunks = []
        for start in range(0, len(tokens), stride):
            window = tokens[start : start + self.MAX_TOKENS]
            chunks.append({"tokens": window, "language": language, "label": label})
            if start + self.MAX_TOKENS >= len(tokens):
                break
        return chunks

