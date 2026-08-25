from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from mecar_automation.agent import AgentLoop, AgentSettings, request_agent_stop
from mecar_automation.engine import AutomationEngine
from mecar_automation.errors import ValidationError
from mecar_automation.health import build_health_report
from mecar_automation.license_health import LicenseProbeSettings, probe_license_status
from mecar_automation.supervisor import ResourceCapacity
from mecar_automation.util import sha256_file

from .support import PROFILES, manifest


class AgentAndHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_agent_settings_bounds_and_disabled_default(self) -> None:
        self.assertFalse(AgentSettings.from_config(None).enabled)
        for invalid in (0, 0.01, 3601, True, "5"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                AgentSettings.from_config({"enabled": True, "poll_interval_sec": invalid})

    def test_agent_loop_gracefully_consumes_stop_marker(self) -> None:
        engine = AutomationEngine(self.root / "runtime-agent", PROFILES, minimum_free_disk_mb=0)
        settings = AgentSettings(enabled=True, poll_interval_sec=0.1, max_jobs_per_cycle=1)
        entered = threading.Event()
        cycles: list[int] = []

        def cycle() -> dict:
            cycles.append(len(cycles) + 1)
            entered.set()
            return {"intake": [], "recovery": [], "jobs": [], "archive": [], "outbox": []}

        loop = AgentLoop(engine, settings, cycle)
        result: list[dict] = []
        worker = threading.Thread(target=lambda: result.append(loop.run()))
        worker.start()
        self.assertTrue(entered.wait(1))
        request_agent_stop(engine.runtime_root, actor="test")
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result[0]["state"], "STOPPED")
        self.assertGreaterEqual(result[0]["cycle_count"], 1)
        self.assertFalse(loop.stop_path.exists())

    def test_resource_gate_wait_is_not_an_engineering_failure(self) -> None:
        runtime = self.root / "runtime-resource"
        blocked = AutomationEngine(
            runtime,
            PROFILES,
            capacity=ResourceCapacity(cpu=0, memory_mb=1024),
            minimum_free_disk_mb=0,
        )
        blocked.submit(manifest("resource-wait"))
        first = blocked.run_one()
        self.assertEqual(first["state"], "WAITING_RESOURCE")
        self.assertEqual(first["attempts"][0]["state"], "INTERRUPTED")
        self.assertEqual(first["artifacts"], [])
        self.assertEqual(first["transitions"][-1]["reason_code"], "RESOURCE_CAPACITY_UNAVAILABLE")
        self.assertTrue(Path(first["attempts"][0]["workdir"]).joinpath("resource-wait.json").is_file())

        resumed = AutomationEngine(
            runtime,
            PROFILES,
            capacity=ResourceCapacity(cpu=1, memory_mb=1024),
            minimum_free_disk_mb=0,
        )
        self.assertEqual(resumed.database.retry("resource-wait"), "QUEUED")
        final = resumed.run_one()
        self.assertEqual(final["state"], "SUCCEEDED")
        self.assertEqual(len(final["attempts"]), 2)

    def _license_settings(self, executable: Path, **overrides) -> LicenseProbeSettings:
        values = {
            "adapter": "lmutil",
            "machine_enabled": True,
            "external_enabled": True,
            "executable": executable,
            "executable_sha256": sha256_file(executable),
            "server": "1055@license-host",
            "features": ("ansys_structures",),
            "timeout_sec": 1.0,
        }
        values.update(overrides)
        return LicenseProbeSettings(**values)

    def test_license_probe_requires_two_gates_without_invoking_runner(self) -> None:
        calls: list[list[str]] = []

        def forbidden(command, **kwargs):
            del kwargs
            calls.append(command)
            raise AssertionError("runner must not be called")

        disabled = probe_license_status(LicenseProbeSettings(), runner=forbidden)
        self.assertEqual(disabled["status"], "DISABLED")
        executable = self.root / "lmutil.exe"
        executable.write_bytes(b"fake")
        blocked = probe_license_status(
            self._license_settings(executable, machine_enabled=False),
            runner=forbidden,
        )
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertFalse(blocked["live_access_attempted"])
        self.assertEqual(calls, [])

    def test_license_probe_strict_command_and_parser_with_fake_runner(self) -> None:
        executable = self.root / "lmutil.exe"
        executable.write_bytes(b"approved fake lmutil")
        captured: list[list[str]] = []

        def fake_runner(command, **kwargs):
            captured.append(command)
            self.assertFalse(kwargs["shell"])
            self.assertEqual(kwargs["timeout"], 1.0)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "license-host: license server UP (MASTER) v11.19\n"
                    "Users of ansys_structures:  (Total of 2 licenses issued;  Total of 1 license in use)\n"
                ),
                stderr="",
            )

        result = probe_license_status(self._license_settings(executable), runner=fake_runner)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["features"]["ansys_structures"]["available"], 1)
        self.assertEqual(captured[0][1:], ["lmstat", "-a", "-c", "1055@license-host"])
        self.assertNotIn("output", result)

    def test_license_probe_hash_and_parse_fail_closed(self) -> None:
        executable = self.root / "lmstat.exe"
        executable.write_bytes(b"fake lmstat")
        calls = 0

        def fake_runner(command, **kwargs):
            nonlocal calls
            del kwargs
            calls += 1
            return subprocess.CompletedProcess(command, 0, stdout="unexpected", stderr="")

        wrong_hash = self._license_settings(executable, executable_sha256="0" * 64)
        self.assertEqual(probe_license_status(wrong_hash, runner=fake_runner)["status"], "ERROR")
        self.assertEqual(calls, 0)
        parsed = probe_license_status(self._license_settings(executable), runner=fake_runner)
        self.assertEqual(parsed["reason_code"], "LICENSE_PROBE_PARSE_FAILED")
        self.assertEqual(calls, 1)

    def test_health_contains_system_queue_provider_and_recent_error_status(self) -> None:
        engine = AutomationEngine(self.root / "runtime-health", PROFILES, minimum_free_disk_mb=0)
        engine.submit(manifest("health-failure", mode="failure"))
        engine.run_one()
        config = {
            "external_execution_enabled": False,
            "external_notification_enabled": False,
            "notification": {"adapter": "fake"},
        }
        report = build_health_report(engine, config, LicenseProbeSettings())
        self.assertEqual(report["status"], "OK")
        self.assertIn("logical_count", report["system"]["cpu"])
        self.assertIn("available_mb", report["system"]["ram"])
        self.assertTrue(report["system"]["disk"]["reserve_ok"])
        self.assertEqual(report["queue"]["job_states"]["FAILED"], 1)
        self.assertEqual(report["recent_errors"][0]["source"], "analysis")
        self.assertFalse(report["providers"]["license"]["live_access_attempted"])
        self.assertFalse(report["providers"]["solver"]["machine_external_execution_enabled"])


if __name__ == "__main__":
    unittest.main()
