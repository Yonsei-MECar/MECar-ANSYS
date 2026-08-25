from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mecar_automation.cli import build_parser, main

from .support import EXAMPLES, PROFILES, manifest


class CliTests(unittest.TestCase):
    def test_all_required_commands_parse(self) -> None:
        parser = build_parser()
        cases = [
            ["submit", "manifest.json"],
            ["list"],
            ["show", "job"],
            ["cancel", "job"],
            ["retry", "job"],
            ["pause"],
            ["resume"],
            ["drain"],
            ["archive"],
            ["archive-retry"],
            ["agent"],
            ["agent-stop"],
            ["verify"],
            ["health"],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                self.assertEqual(parser.parse_args(arguments).command, arguments[0])

    def test_submit_drain_show_verify_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            common = ["--runtime-root", directory, "--profiles", str(PROFILES)]
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                self.assertEqual(main(common + ["submit", str(EXAMPLES / "manifests" / "valid-dummy.json")]), 0)
                self.assertEqual(main(common + ["drain", "--max-jobs", "1"]), 0)
                self.assertEqual(main(common + ["show", "dummy-success-001"]), 0)
                self.assertEqual(main(common + ["verify", "--job-id", "dummy-success-001"]), 0)
                self.assertEqual(main(common + ["health"]), 0)
            self.assertIn("SUCCEEDED", output.getvalue())

    def test_app_config_wires_local_artifacts_and_fake_nas_archive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            fake_nas = root / "fake-nas"
            config_path = root / "app.json"
            config_path.write_text(
                json.dumps(
                    {
                        "external_archive_enabled": True,
                        "minimum_free_disk_mb": 0,
                        "artifacts": {
                            "local_root": "immutable-local",
                            "archive": {
                                "adapter": "nas",
                                "route_id": "local-test-route",
                                "root": str(fake_nas),
                                "roles": ["summary_report"],
                                "external_enabled": True,
                                "max_attempts": 2,
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            common = [
                "--runtime-root",
                str(runtime),
                "--profiles",
                str(PROFILES),
                "--config",
                str(config_path),
            ]
            output = StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                self.assertEqual(
                    main(common + ["submit", str(EXAMPLES / "manifests" / "valid-dummy.json")]),
                    0,
                )
                self.assertEqual(main(common + ["drain", "--max-jobs", "1"]), 0)
                self.assertEqual(main(common + ["archive"]), 0)
                self.assertEqual(main(common + ["archive-retry", "--job-id", "dummy-success-001"]), 0)
            self.assertTrue((runtime / "immutable-local" / "sha256").is_dir())
            self.assertTrue((fake_nas / "sha256").is_dir())
            self.assertIn("ARCHIVE_VERIFIED", output.getvalue())

    def test_archive_enable_switches_reject_string_coercion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "bad-app.json"
            config_path.write_text(
                json.dumps(
                    {
                        "external_archive_enabled": "false",
                        "artifacts": {"local_root": "artifacts", "archive": {"adapter": "disabled"}},
                    }
                ),
                encoding="utf-8",
            )
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(
                    main(
                        [
                            "--runtime-root",
                            str(root / "runtime"),
                            "--profiles",
                            str(PROFILES),
                            "--config",
                            str(config_path),
                            "health",
                        ]
                    ),
                    2,
                )

    def test_behavioral_cancel_retry_pause_resume_agent_and_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            config_path = root / "app.json"
            config_path.write_text(
                json.dumps(
                    {
                        "external_execution_enabled": False,
                        "external_archive_enabled": False,
                        "external_license_probe_enabled": False,
                        "minimum_free_disk_mb": 0,
                        "resources": {"cpu": 1, "memory_mb": 512, "licenses": {}},
                        "notification": {"adapter": "fake"},
                        "recipient_policy": {"version": "1", "allowed_domains": [], "allowed_addresses": []},
                        "artifacts": {"local_root": "artifacts", "archive": {"adapter": "disabled"}},
                        "license_probe": {"adapter": "disabled"},
                        "agent": {
                            "enabled": True,
                            "poll_interval_sec": 0.1,
                            "max_jobs_per_cycle": 10,
                            "max_archive_operations_per_cycle": 10,
                            "max_stale_attempts": 2,
                        },
                    }
                ),
                encoding="utf-8",
            )
            request_path = root / "request.json"
            request_path.write_text(json.dumps(manifest("cli-behavior")), encoding="utf-8")
            common = [
                "--runtime-root",
                str(runtime),
                "--profiles",
                str(PROFILES),
                "--config",
                str(config_path),
            ]

            def invoke(arguments: list[str]) -> tuple[int, dict]:
                stdout = StringIO()
                stderr = StringIO()
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    code = main(common + arguments)
                text = stdout.getvalue() if stdout.getvalue().strip() else stderr.getvalue()
                return code, json.loads(text)

            self.assertEqual(invoke(["pause"]), (0, {"dispatcher": "PAUSED"}))
            self.assertEqual(invoke(["submit", str(request_path)])[0], 0)
            code, drained = invoke(["drain", "--max-jobs", "1"])
            self.assertEqual(code, 0)
            self.assertEqual(drained["jobs"], [])
            self.assertEqual(invoke(["cancel", "cli-behavior"])[1]["state"], "CANCELLED")
            self.assertEqual(invoke(["retry", "cli-behavior"])[1]["state"], "QUEUED")
            self.assertEqual(invoke(["resume"]), (0, {"dispatcher": "RUNNING"}))
            self.assertEqual(invoke(["agent-stop"])[1]["state"], "STOP_REQUESTED")
            code, agent = invoke(["agent", "--once"])
            self.assertEqual(code, 0)
            self.assertEqual(agent["state"], "STOPPED")
            self.assertEqual(agent["last_cycle_summary"]["jobs"], 1)
            self.assertEqual(invoke(["show", "cli-behavior"])[1]["state"], "SUCCEEDED")
            code, archive = invoke(["archive"])
            self.assertEqual(code, 0)
            self.assertEqual(archive["archive"], [])
            code, health = invoke(["health"])
            self.assertEqual(code, 0)
            self.assertEqual(health["status"], "OK")
            self.assertIn("cpu", health["system"])
            self.assertIn("license", health["providers"])


if __name__ == "__main__":
    unittest.main()
