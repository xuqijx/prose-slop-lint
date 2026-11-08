"""Command-line entry for prose-slop-lint."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from prose_slop_lint import __version__
from prose_slop_lint.rules import RULES
from prose_slop_lint.scan import Finding, scan_text

PROSE_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".adoc", ".asciidoc"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache"}

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2


class Colors:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def wrap(self, code: str, text: str) -> str:
        if not self.enabled or not text:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, text: str) -> str:
        return self.wrap("1", text)

    def cyan(self, text: str) -> str:
        return self.wrap("36", text)

    def green(self, text: str) -> str:
        return self.wrap("32", text)

    def dim(self, text: str) -> str:
        return self.wrap("2", text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prose-slop-lint",
        description=(
            "Scan README files, docs, and short descriptions for padded, "
            "AI-flavored phrasing. Matches are regex heuristics, not a "
            "language-model judgment. No network access."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or directories to scan. Reads stdin when there are no paths and stdin is piped. Use - for stdin.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print findings as JSON.",
    )
    parser.add_argument(
        "--rules",
        action="store_true",
        help="List rule ids and exit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"prose-slop-lint {__version__}",
    )
    color = parser.add_mutually_exclusive_group()
    color.add_argument("--color", action="store_true", help="Colorize the text report.")
    color.add_argument("--no-color", action="store_true", help="Do not colorize the text report.")
    return parser


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def iter_input_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    missing: list[str] = []
    for raw in paths:
        if raw == "-":
            continue
        path = Path(raw)
        if path.is_file():
            files.append(path)
            continue
        if path.is_dir():
            for dirpath, dirnames, filenames in os.walk(path):
                dirnames[:] = sorted(
                    name
                    for name in dirnames
                    if name not in SKIP_DIRS and not name.startswith(".")
                )
                for name in sorted(filenames):
                    candidate = Path(dirpath) / name
                    if candidate.suffix.lower() in PROSE_EXTENSIONS:
                        files.append(candidate)
            continue
        missing.append(raw)
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"Path not found: {joined}")
    return files


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def collect(paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    want_stdin = (not paths) or ("-" in paths)
    for path in iter_input_files(paths):
        findings.extend(scan_text(display_path(path), read_text(path)))
    if want_stdin:
        findings.extend(scan_text("<stdin>", sys.stdin.read()))
    findings.sort(key=lambda item: (item.file, item.line, item.column, item.rule_id))
    return findings


def emit_json(findings: list[Finding]) -> None:
    payload = {
        "tool": "prose-slop-lint",
        "heuristics_only": True,
        "count": len(findings),
        "findings": [item.to_dict() for item in findings],
    }
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def emit_text(findings: list[Finding], colors: Colors) -> None:
    print(colors.bold("prose-slop-lint"))
    print("Pattern heuristics only. A match is not a language-model judgment.")
    print()
    if not findings:
        print("No findings.")
        return
    for item in findings:
        header = f"{item.file}:{item.line}: {item.rule_id}"
        print(colors.bold(header))
        print(f"  excerpt: {item.excerpt}")
        print(colors.dim(f"  why:     {item.why}"))
        print(colors.green(f"  rewrite: {item.rewrite}"))
        print()
    noun = "finding" if len(findings) == 1 else "findings"
    print(f"{len(findings)} {noun}.")


def use_color(args: argparse.Namespace) -> bool:
    if args.no_color or args.json:
        return False
    if args.color:
        return True
    return sys.stdout.isatty() and not args.no_color


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.rules:
        for rule in RULES:
            print(f"{rule.rule_id}\t{rule.why}")
        return EXIT_CLEAN
    if not args.paths and sys.stdin.isatty():
        parser.print_help(sys.stderr)
        return EXIT_USAGE
    try:
        findings = collect(args.paths)
    except (FileNotFoundError, UnicodeDecodeError, OSError) as exc:
        print(f"prose-slop-lint: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        emit_json(findings)
    else:
        emit_text(findings, Colors(use_color(args)))
    return EXIT_FINDINGS if findings else EXIT_CLEAN
