from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".c": "C",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
}

EXCLUDED_PATH_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(^|/)node_modules/",
        r"(^|/)vendor/",
        r"(^|/)dist/",
        r"(^|/)build/",
        r"(^|/)__pycache__/",
        r"\.min\.js$",
        r"package-lock\.json$",
        r"go\.sum$",
        r"yarn\.lock$",
        r"\.generated\.",
    )
]

PRIORITY_PREFIXES = ("src/", "lib/", "app/", "pkg/", "internal/")


@dataclass(frozen=True)
class TreeEntry:
    path: str
    type: str
    size: int
    sha: str
    url: str | None = None

    @property
    def extension(self) -> str:
        dot_index = self.path.rfind(".")
        return self.path[dot_index:].lower() if dot_index >= 0 else ""

    @property
    def language(self) -> str:
        return LANGUAGE_BY_EXTENSION.get(self.extension, "Code")


class FileSampler:
    def __init__(self, min_bytes: int = 200, max_bytes: int = 100 * 1024):
        self.min_bytes = min_bytes
        self.max_bytes = max_bytes

    def sample(self, tree: list[TreeEntry], max_files: int = 30) -> list[TreeEntry]:
        candidates = [entry for entry in tree if self._is_source_candidate(entry)]
        if len(candidates) <= max_files:
            return sorted(candidates, key=lambda entry: entry.path)

        scored = [(self._weight(entry), entry) for entry in candidates]
        scored.sort(key=lambda item: (-item[0], item[1].path))

        selected: list[TreeEntry] = []
        languages = sorted({entry.language for _, entry in scored})
        per_language_target = max(1, max_files // max(1, len(languages)))

        for language in languages:
            language_entries = [entry for _, entry in scored if entry.language == language]
            selected.extend(language_entries[:per_language_target])
            if len(selected) >= max_files:
                break

        seen = {entry.path for entry in selected}
        for _, entry in scored:
            if len(selected) >= max_files:
                break
            if entry.path not in seen:
                selected.append(entry)
                seen.add(entry.path)

        return sorted(selected[:max_files], key=lambda entry: entry.path)

    def _is_source_candidate(self, entry: TreeEntry) -> bool:
        if entry.type != "blob":
            return False
        if entry.extension not in LANGUAGE_BY_EXTENSION:
            return False
        if entry.size < self.min_bytes or entry.size > self.max_bytes:
            return False
        return not any(pattern.search(entry.path) for pattern in EXCLUDED_PATH_PATTERNS)

    def _weight(self, entry: TreeEntry) -> float:
        weight = 1.0
        normalized_path = entry.path.lower()
        if normalized_path.startswith(PRIORITY_PREFIXES):
            weight *= 2.0
        if entry.size >= 20 * 1024:
            weight *= 1.5
        weight *= 0.95 + (stable_float(entry.path) * 0.1)
        return weight


def infer_language(path: str) -> str:
    dot_index = path.rfind(".")
    extension = path[dot_index:].lower() if dot_index >= 0 else ""
    return LANGUAGE_BY_EXTENSION.get(extension, "Code")


def stable_float(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF

