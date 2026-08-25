from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from mecar_automation.engine import AutomationEngine

from .support import PROFILES, manifest


class RecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.engine = AutomationEngine(self.root, PROFILES, minimum_free_disk_mb=0)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_stale_attempt_requeues_then_fails_at_limit(self) -> None:
        self.engine.submit(manifest("stale"))
        first = self.engine.database.claim_next(self.engine.work_root)
        self.engine.database.record_attempt_pid(first.attempt_id, 2147483000)
        recovered = self.engine.database.reconcile_stale(lambda pid: False, max_attempts=2)
        self.assertEqual(recovered[0]["state"], "QUEUED")
        second = self.engine.database.claim_next(self.engine.work_root)
        self.engine.database.record_attempt_pid(second.attempt_id, 2147483001)
        recovered = self.engine.database.reconcile_stale(lambda pid: False, max_attempts=2)
        self.assertEqual(recovered[0]["state"], "FAILED")
        self.assertEqual(self.engine.database.show_job("stale")["attempts"][-1]["state"], "INTERRUPTED")

    def test_running_live_process_is_not_reconciled(self) -> None:
        self.engine.submit(manifest("live"))
        attempt = self.engine.database.claim_next(self.engine.work_root)
        self.engine.database.record_attempt_pid(attempt.attempt_id, 1234)
        self.assertEqual(self.engine.database.reconcile_stale(lambda pid: True), [])
        self.assertEqual(self.engine.database.latest_job_state("live"), "RUNNING")

    def test_audit_tables_are_append_only(self) -> None:
        self.engine.submit(manifest("append-only"))
        connection = sqlite3.connect(self.engine.database.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE jobs SET adapter='changed' WHERE job_id='append-only'")
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

