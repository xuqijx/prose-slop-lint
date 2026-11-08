"""Checks for rules, exit codes, fixtures, and the four README files."""

from __future__ import annotations

import ast
import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prose_slop_lint.cli import main  # noqa: E402
from prose_slop_lint.rules import RULES  # noqa: E402
from prose_slop_lint.scan import scan_text  # noqa: E402

REQUIRED_FINDING_KEYS = ("rule_id", "file", "line", "excerpt", "why", "rewrite")
README_FILES = (
    "README.md",
    "README.zh-CN.md",
    "README.zh-TW.md",
    "README.ja.md",
)
NETWORK_MODULES = {
    "urllib",
    "http",
    "socket",
    "requests",
    "openai",
    "httplib",
    "ftplib",
    "smtplib",
    "telnetlib",
}


class LintTests(unittest.TestCase):
    def test_at_least_twelve_distinct_rules(self) -> None:
        rule_ids = [rule.rule_id for rule in RULES]
        self.assertGreaterEqual(len(rule_ids), 12)
        self.assertEqual(len(rule_ids), len(set(rule_ids)))

    def test_sloppy_fixture_fires_every_rule(self) -> None:
        text = (ROOT / "fixtures" / "sloppy-example.md").read_text(encoding="utf-8")
        findings = scan_text("fixtures/sloppy-example.md", text)
        fired = {item.rule_id for item in findings}
        self.assertEqual(fired, {rule.rule_id for rule in RULES})
        for item in findings:
            payload = item.to_dict()
            for key in REQUIRED_FINDING_KEYS:
                self.assertIn(key, payload)
                self.assertTrue(payload[key] or payload[key] == 0)
            self.assertIsInstance(item.line, int)
            self.assertGreater(item.line, 0)
            self.assertNotEqual(item.rewrite.strip().lower(), item.excerpt.strip().lower())

    def test_cleaner_fixture_has_no_findings(self) -> None:
        sloppy = scan_text(
            "sloppy",
            (ROOT / "fixtures" / "sloppy-example.md").read_text(encoding="utf-8"),
        )
        cleaner = scan_text(
            "cleaner",
            (ROOT / "fixtures" / "cleaner-example.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(cleaner, [])
        self.assertLess(len(cleaner), len(sloppy))

    def test_specific_rewrites_are_plainer(self) -> None:
        text = (ROOT / "fixtures" / "sloppy-example.md").read_text(encoding="utf-8")
        by_rule: dict[str, list] = {}
        for item in scan_text("fixtures/sloppy-example.md", text):
            by_rule.setdefault(item.rule_id, []).append(item)
        self.assertIn("look at", by_rule["delve"][0].rewrite.lower())
        self.assertNotIn("delve", by_rule["delve"][0].rewrite.lower())
        self.assertIn("sorts notes and groups", by_rule["not-only-but-also"][0].rewrite.lower())
        self.assertIn("treat this page as fiction", by_rule["in-conclusion"][0].rewrite.lower())
        self.assertNotIn("conclusion", by_rule["in-conclusion"][0].rewrite.lower())
        self.assertTrue(by_rule["persona-opener"][0].rewrite.lower().startswith("the sample stays"))

    def test_code_spans_are_ignored(self) -> None:
        text = "\n".join(
            [
                "The verb `delve` is quoted here.",
                "```",
                "We delve into a rich tapestry in the digital landscape.",
                "```",
                "A normal sentence about folders.",
            ]
        )
        self.assertEqual(scan_text("quoted.md", text), [])
        flagged = scan_text("mixed.md", "We leverage the `delve` example.")
        self.assertEqual([item.rule_id for item in flagged], ["leverage-verb"])

    def test_cli_exit_codes(self) -> None:
        sloppy = self._run("fixtures/sloppy-example.md")
        cleaner = self._run("fixtures/cleaner-example.md")
        missing = self._run("fixtures/missing-example.md")
        self.assertEqual(sloppy.returncode, 1, sloppy.stderr)
        self.assertEqual(cleaner.returncode, 0, cleaner.stderr)
        self.assertEqual(missing.returncode, 2, missing.stderr)
        self.assertIn("fixtures/sloppy-example.md", sloppy.stdout)
        self.assertIn("excerpt:", sloppy.stdout)
        self.assertIn("why:", sloppy.stdout)
        self.assertIn("rewrite:", sloppy.stdout)
        self.assertIn("No findings.", cleaner.stdout)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["fixtures/cleaner-example.md"]), 0)
            self.assertEqual(main(["fixtures/sloppy-example.md"]), 1)
            self.assertEqual(main(["fixtures/missing-example.md"]), 2)

    def test_json_report_shape(self) -> None:
        completed = self._run("--json", "fixtures/sloppy-example.md")
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["heuristics_only"])
        self.assertEqual(payload["count"], len(payload["findings"]))
        self.assertGreaterEqual(len({item["rule_id"] for item in payload["findings"]}), 12)
        for item in payload["findings"]:
            for key in REQUIRED_FINDING_KEYS:
                self.assertIn(key, item)
            self.assertIsInstance(item["line"], int)
            self.assertTrue(str(item["excerpt"]).strip())
            self.assertTrue(str(item["why"]).strip())
            self.assertTrue(str(item["rewrite"]).strip())

    def test_stdin_exit_code(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "prose_slop_lint", "-"],
            input="We delve into the fictional notes.\n",
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("<stdin>", completed.stdout)

    def test_readme_files_exist_and_link_languages(self) -> None:
        bodies = {}
        for name in README_FILES:
            path = ROOT / name
            self.assertTrue(path.is_file(), name)
            text = path.read_text(encoding="utf-8")
            bodies[name] = text
            for link in README_FILES:
                self.assertIn(f"]({link})", text)
            self.assertIn("fixtures/sloppy-example.md", text)
            self.assertIn("docs/demo.png", text)
            findings = scan_text(name, text)
            self.assertEqual(
                findings,
                [],
                f"{name} tripped: {[item.rule_id for item in findings]}",
            )
        self.assertIn("offline command-line", bodies["README.md"].lower())
        self.assertIn("离线", bodies["README.zh-CN.md"])
        self.assertIn("離線", bodies["README.zh-TW.md"])
        self.assertIn("オフライン", bodies["README.ja.md"])
        self.assertNotEqual(bodies["README.zh-CN.md"], bodies["README.zh-TW.md"])
        self.assertIn("虚构", bodies["README.zh-CN.md"])
        self.assertIn("虛構", bodies["README.zh-TW.md"])
        self.assertIn("フィクション", bodies["README.ja.md"])
        self.assertIn("fictional", bodies["README.md"].lower())
        self.assertIn("heuristic", bodies["README.md"].lower())
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Permission is hereby granted", license_text)
        self.assertTrue((ROOT / "docs" / "demo.png").is_file())

    def test_sources_do_not_import_network_modules(self) -> None:
        for path in (ROOT / "prose_slop_lint").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    self.assertNotIn(module.split(".")[0], NETWORK_MODULES, path.name)

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "prose_slop_lint", *args],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
