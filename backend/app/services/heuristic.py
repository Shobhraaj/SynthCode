from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, asdict


SIGNAL_WEIGHTS = {
    "comment_uniformity": 0.20,
    "naming_entropy": 0.20,
    "boilerplate_ratio": 0.15,
    "structure_repetition": 0.20,
    "comment_code_ratio": 0.10,
    "import_style": 0.15,
}

IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
FUNCTION_RE = re.compile(r"\b(?:def|function|func|fn|public|private|protected|static|async)\s+[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)")
IMPORT_RE = re.compile(r"^\s*(?:import|from|const\s+.+require|use\s+|#include)", re.MULTILINE)
BOILERPLATE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"try\s*:",
        r"try\s*\{",
        r"catch\s*\(",
        r"except\s+",
        r"if\s+[^:\n]+is\s+None",
        r"if\s*\([^)]*==\s*null\)",
        r"if\s*\([^)]*===\s*undefined\)",
        r"return\s+None",
        r"return\s+null",
        r"console\.log",
        r"logger\.",
        r"raise\s+ValueError",
        r"throw\s+new\s+Error",
        r"TODO:",
    )
]


@dataclass(frozen=True)
class HeuristicResult:
    comment_uniformity: float
    naming_entropy: float
    boilerplate_ratio: float
    structure_repetition: float
    comment_code_ratio: float
    import_style: float
    composite: float

    def asdict(self) -> dict[str, float]:
        return asdict(self)


class HeuristicAnalyzer:
    def analyze_file(self, content: str, language: str) -> HeuristicResult:
        scores = {
            "comment_uniformity": self._comment_uniformity(content),
            "naming_entropy": self._naming_entropy(content),
            "boilerplate_ratio": self._boilerplate_ratio(content),
            "structure_repetition": self._structure_repetition(content, language),
            "comment_code_ratio": self._comment_code_ratio(content),
            "import_style": self._import_style(content),
        }
        composite = sum(scores[name] * SIGNAL_WEIGHTS[name] for name in SIGNAL_WEIGHTS)
        return HeuristicResult(**scores, composite=clamp(composite))

    def _comment_uniformity(self, content: str) -> float:
        lines = content.splitlines()
        comment_lines = [index for index, line in enumerate(lines) if is_comment_line(line)]
        if len(comment_lines) < 3:
            return 0.15
        gaps = [right - left for left, right in zip(comment_lines, comment_lines[1:])]
        mean = sum(gaps) / len(gaps)
        variance = sum((gap - mean) ** 2 for gap in gaps) / len(gaps)
        return clamp(1.0 - min(math.sqrt(variance) / 10, 1.0))

    def _naming_entropy(self, content: str) -> float:
        identifiers = [
            token.lower()
            for token in IDENTIFIER_RE.findall(content)
            if len(token) > 2 and token not in PYTHON_AND_JS_KEYWORDS
        ]
        if len(identifiers) < 10:
            return 0.2
        entropy = shannon_entropy("".join(identifiers))
        return clamp(1.0 - ((entropy - 2.5) / 2.5))

    def _boilerplate_ratio(self, content: str) -> float:
        lines = max(1, len(content.splitlines()))
        hits = sum(len(pattern.findall(content)) for pattern in BOILERPLATE_PATTERNS)
        return clamp(hits / max(4, lines / 20))

    def _structure_repetition(self, content: str, language: str) -> float:
        shapes = self._python_function_shapes(content) if language.lower() == "python" else FUNCTION_RE.findall(content)
        if len(shapes) < 3:
            return 0.2
        bags = [set(IDENTIFIER_RE.findall(shape.lower())) for shape in shapes]
        similarities = []
        for index, left in enumerate(bags):
            for right in bags[index + 1 :]:
                if left or right:
                    similarities.append(len(left & right) / len(left | right))
        return clamp(sum(similarities) / max(1, len(similarities)))

    def _comment_code_ratio(self, content: str) -> float:
        lines = [line for line in content.splitlines() if line.strip()]
        if not lines:
            return 0.0
        comments = sum(1 for line in lines if is_comment_line(line))
        ratio = comments / len(lines)
        return clamp(abs(ratio - 0.18) / 0.22)

    def _import_style(self, content: str) -> float:
        imports = IMPORT_RE.findall(content)
        if len(imports) < 3:
            return 0.15
        import_lines = [line.strip() for line in content.splitlines() if IMPORT_RE.match(line)]
        alphabetized = import_lines == sorted(import_lines, key=str.lower)
        contiguous = max_import_block_length(content) >= len(import_lines) * 0.8
        return clamp((0.55 if alphabetized else 0.2) + (0.35 if contiguous else 0.0))

    def _python_function_shapes(self, content: str) -> list[str]:
        try:
            module = ast.parse(content)
        except SyntaxError:
            return FUNCTION_RE.findall(content)
        return [
            f"{node.name}({len(node.args.args)})/{len(node.body)}"
            for node in ast.walk(module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]


def is_comment_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(("#", "//", "/*", "*", '"""', "'''"))


def max_import_block_length(content: str) -> int:
    longest = 0
    current = 0
    for line in content.splitlines():
        if IMPORT_RE.match(line):
            current += 1
            longest = max(longest, current)
        elif line.strip():
            current = 0
    return longest


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {character: value.count(character) for character in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def clamp(value: float) -> float:
    return round(min(1.0, max(0.0, value)), 4)


PYTHON_AND_JS_KEYWORDS = {
    "and",
    "as",
    "async",
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "def",
    "else",
    "except",
    "false",
    "for",
    "from",
    "function",
    "if",
    "import",
    "in",
    "let",
    "none",
    "null",
    "return",
    "true",
    "try",
    "var",
    "while",
}

