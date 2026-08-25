from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from mecar_fluent2d.runner import run_case, run_sweep


ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "fixtures" / "fake_fluent.py"
MANIFEST = ROOT / "config" / "golden-naca0012.json"


class RunnerTests(unittest.TestCase):
    def test_fake_subprocess_success_and_verified_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = run_case(MANIFEST, temporary, command_override=[sys.executable, str(FAKE)])
            self.assertTrue(first["process"]["passed"])
            self.assertTrue(first["engineering"]["passed"])
            self.assertFalse(first["authority"]["authoritative"])
            second = run_case(MANIFEST, temporary, command_override=[sys.executable, str(FAKE)])
            self.assertTrue(second["resumedSkipped"])

    def test_csv_only_fake_is_engineering_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = run_case(
                MANIFEST,
                temporary,
                command_override=[sys.executable, str(FAKE), "--bad-csv-only"],
            )
            self.assertTrue(result["process"]["passed"])
            self.assertFalse(result["engineering"]["passed"])

    def test_resume_rejects_a_stale_process_failure_and_cleans_extension_journals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = run_case(MANIFEST, temporary, command_override=[sys.executable, str(FAKE)])
            case_dir = Path(first["process"]["phases"][0]["consoleLog"])
            self.assertEqual(case_dir.as_posix(), "logs/console-base.log")
            runtime_case = Path(temporary) / "cases" / first["caseId"]
            stale_extension = runtime_case / "journal" / "extension-999.jou"
            stale_extension.write_text("stale", encoding="ascii")
            report_path = runtime_case / "reports" / "report.json"
            stored = json.loads(report_path.read_text(encoding="utf-8"))
            stored["process"]["passed"] = False
            report_path.write_text(json.dumps(stored), encoding="utf-8")

            second = run_case(MANIFEST, temporary, command_override=[sys.executable, str(FAKE)])
            self.assertFalse(second["resumedSkipped"])
            self.assertTrue(second["process"]["passed"])
            self.assertFalse(stale_extension.exists())

    def test_sweep_continues_after_an_intentional_case_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing_manifest = Path(temporary) / "intentional-missing-case.json"
            result = run_sweep(
                [missing_manifest, MANIFEST],
                temporary,
                command_override=[sys.executable, str(FAKE)],
            )
            self.assertEqual(result["caseCount"], 2)
            self.assertEqual(result["completed"], 1)
            self.assertEqual(result["failed"], 1)
            self.assertIn("InputError", result["cases"][0]["error"])
            self.assertTrue(result["cases"][1]["engineeringPassed"])


if __name__ == "__main__":
    unittest.main()
