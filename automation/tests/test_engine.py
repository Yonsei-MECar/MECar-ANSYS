from __future__ import annotations

import tempfile
import threading
import time
import json
import shutil
import unittest
from pathlib import Path

from mecar_automation.engine import AutomationEngine
from mecar_automation.errors import InvalidTransition, SubmissionConflict, ValidationError
from mecar_automation.supervisor import ResourceCapacity
from mecar_automation.util import load_json

from .support import EXAMPLES, PROFILES, manifest


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.engine = AutomationEngine(
            self.root,
            PROFILES,
            capacity=ResourceCapacity(cpu=2, memory_mb=1024),
            minimum_free_disk_mb=0,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run(self, submission_id: str, mode: str, timeout: float = 2.0) -> dict:
        self.engine.submit(manifest(submission_id, mode=mode, timeout=timeout))
        result = self.engine.run_one()
        assert result is not None
        return result

    def test_success(self) -> None:
        result = self._run("success", "success")
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertTrue(any(item["role"] == "summary_report" for item in result["artifacts"]))
        self.assertTrue(self.engine.verify("success")["valid"])

    def test_declared_failure(self) -> None:
        result = self._run("failure", "failure")
        self.assertEqual(result["state"], "FAILED")

    def test_process_crash(self) -> None:
        result = self._run("crash", "crash")
        self.assertEqual(result["state"], "FAILED")
        self.assertEqual(result["transitions"][-1]["reason_code"], "PROCESS_CRASH")

    def test_hang_times_out_and_process_is_reaped(self) -> None:
        result = self._run("hang", "hang", timeout=0.1)
        self.assertEqual(result["state"], "TIMED_OUT")
        self.assertEqual(result["attempts"][0]["state"], "TIMED_OUT")

    def test_retry_after_failure(self) -> None:
        self._run("retry", "failure")
        self.assertEqual(self.engine.database.retry("retry"), "QUEUED")
        second = self.engine.run_one()
        self.assertEqual(second["state"], "FAILED")
        self.assertEqual(len(second["attempts"]), 2)

    def test_queued_cancel_does_not_start_solver(self) -> None:
        self.engine.submit(manifest("cancelled"))
        self.assertEqual(self.engine.database.request_cancel("cancelled"), "CANCELLED")
        self.assertIsNone(self.engine.run_one())
        with self.assertRaises(InvalidTransition):
            self.engine.database.request_cancel("cancelled")

    def test_running_cancel_terminates_process_tree(self) -> None:
        self.engine.submit(manifest("running-cancel", mode="hang", timeout=5))
        holder: list[dict] = []
        worker = threading.Thread(target=lambda: holder.append(self.engine.run_one()))
        worker.start()
        deadline = time.monotonic() + 2
        while self.engine.database.latest_job_state("running-cancel") != "RUNNING" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.engine.database.request_cancel("running-cancel"), "CANCEL_REQUESTED")
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(holder[0]["state"], "CANCELLED")

    def test_disabled_external_profiles_fail_closed_at_submit(self) -> None:
        for name in ("valid-mapdl-v211.json", "valid-fluent-v211.json"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.engine.submit(load_json(EXAMPLES / "manifests" / name))

    def test_pause_and_resume(self) -> None:
        self.engine.submit(manifest("paused"))
        self.engine.database.set_paused(True)
        self.assertIsNone(self.engine.run_one())
        self.engine.database.set_paused(False)
        self.assertEqual(self.engine.run_one()["state"], "SUCCEEDED")

    def test_profile_is_frozen_at_submission_and_same_version_mutation_conflicts(self) -> None:
        profiles = self.root / "profiles"
        shutil.copytree(PROFILES, profiles)
        engine = AutomationEngine(self.root / "frozen", profiles, minimum_free_disk_mb=0)
        value = manifest("frozen-profile")
        engine.submit(value)
        profile_path = profiles / "dummy-standard-1.0.0.json"
        changed = json.loads(profile_path.read_text(encoding="utf-8"))
        changed["settings"] = {"unapproved_same_version_change": True}
        profile_path.write_text(json.dumps(changed), encoding="utf-8")
        result = engine.run_one()
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertEqual(result["profile_snapshot"]["settings"], {})
        with self.assertRaises(SubmissionConflict):
            engine.submit(value)


if __name__ == "__main__":
    unittest.main()
