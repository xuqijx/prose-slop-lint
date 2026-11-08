"""Scan prose text and build findings.

Fenced code blocks and inline code are skipped so a document can quote a
flagged phrase without reporting itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from prose_slop_lint.rules import RULES

_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"`+[^`\n]*`+")
_RULE_ORDER = {rule.rule_id: index for index, rule in enumerate(RULES)}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    file: str
    line: int
    excerpt: str
    why: str
    rewrite: str
    column: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "file": self.file,
            "line": self.line,
            "excerpt": self.excerpt,
            "why": self.why,
            "rewrite": self.rewrite,
        }


def iter_prose_lines(text: str):
    """Yield (line_number, line) pairs outside Markdown fences."""
    in_fence = False
    fence_char = ""
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\r")
        marker = _FENCE.match(line)
        if marker:
            char = marker.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_char = char
            elif char == fence_char:
                in_fence = False
                fence_char = ""
            continue
        if in_fence:
            continue
        yield lineno, line


def mask_inline_code(line: str) -> str:
    """Replace inline code with spaces so indexes still match the source line."""
    return _INLINE_CODE.sub(lambda match: " " * len(match.group(0)), line)


def tidy(text: str) -> str:
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"^[ \t]*[,;:]+[ \t]*", "", text)
    text = text.strip()
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def excerpt_for(line: str, start: int, end: int, limit: int = 220) -> str:
    stripped = line.strip()
    if len(stripped) <= limit:
        return stripped
    radius = limit // 2
    left = max(0, start - radius)
    right = min(len(line), max(end, start + 1) + radius)
    snippet = line[left:right].strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(line):
        snippet = snippet + "..."
    return snippet


def scan_text(filename: str, text: str) -> list[Finding]:
    """Return findings for one document. `filename` is printed as given."""
    findings: list[Finding] = []
    for lineno, line in iter_prose_lines(text):
        masked = mask_inline_code(line)
        for rule in RULES:
            for match in rule.pattern.finditer(masked):
                replacement = rule.replace(match)
                rewrite = tidy(line[: match.start()] + replacement + line[match.end() :])
                if not rewrite:
                    rewrite = "(delete this phrase)"
                findings.append(
                    Finding(
                        rule_id=rule.rule_id,
                        file=filename,
                        line=lineno,
                        column=match.start() + 1,
                        excerpt=excerpt_for(line, match.start(), match.end()),
                        why=rule.why,
                        rewrite=rewrite,
                    )
                )
    findings.sort(key=lambda item: (item.file, item.line, item.column, _RULE_ORDER[item.rule_id]))
    return findings
