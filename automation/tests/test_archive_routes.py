from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from mecar_automation.artifacts import ArchiveRoute, NasArtifactStorage
from mecar_automation.engine import AutomationEngine
from mecar_automation.util import sha256_file

from .support import PROFILES, manifest


class ArchiveRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _route(
        self,
        root: Path,
        *,
        route_id: str,
        machine_enabled: bool,
        external_enabled: bool,
        max_attempts: int = 3,
    ) -> ArchiveRoute:
        return ArchiveRoute(
            route_id=route_id,
            root=root,
            roles=frozenset({"summary_report"}),
            machine_enabled=machine_enabled,
            external_enabled=external_enabled,
            max_attempts=max_attempts,
        )

    def test_both_external_enable_gates_are_required_without_touching_target(self) -> None:
        for index, (machine_enabled, route_enabled) in enumerate(((False, True), (True, False)), 1):
            with self.subTest(machine_enabled=machine_enabled, route_enabled=route_enabled):
                target = self.root / f"untouched-{index}"
                engine = AutomationEngine(
                    self.root / f"runtime-{index}",
                    PROFILES,
                    minimum_free_disk_mb=0,
                    archive_route=self._route(
                        target,
                        route_id=f"gate-{index}",
                        machine_enabled=machine_enabled,
                        external_enabled=route_enabled,
                    ),
                )
                job_id = f"archive-gate-{index}"
                engine.submit(manifest(job_id))
                result = engine.run_one()
                self.assertEqual(result["state"], "SUCCEEDED")
                self.assertEqual(engine.drain_archives()[0]["state"], "BLOCKED")
                self.assertFalse(target.exists())
                shown = engine.database.show_job(job_id)
                self.assertEqual(shown["state"], "SUCCEEDED")
                self.assertEqual(shown["archive_operations"][0]["state"], "BLOCKED")

    def test_verified_content_addressed_archive_is_idempotent(self) -> None:
        target = self.root / "fake-nas"
        engine = AutomationEngine(
            self.root / "runtime-success",
            PROFILES,
            minimum_free_disk_mb=0,
            archive_route=self._route(
                target,
                route_id="verified-route",
                machine_enabled=True,
                external_enabled=True,
            ),
        )
        engine.submit(manifest("archive-success"))
        self.assertEqual(engine.run_one()["state"], "SUCCEEDED")
        archived = engine.drain_archives()
        self.assertEqual(archived[0]["state"], "SUCCEEDED")
        operation = engine.database.list_archive_operations("archive-success")[0]
        destination = Path(operation["archive_path"])
        self.assertTrue(destination.is_file())
        self.assertEqual(sha256_file(destination), operation["expected_sha256"])
        self.assertEqual(list((target / ".staging").glob("*.part")), [])
        self.assertEqual(engine.drain_archives(), [])
        self.assertEqual(engine.retry_archives("archive-success"), [])
        self.assertEqual(engine.verify("archive-success")["archive_status"], "COMPLETE")

    def test_archive_only_manual_retry_does_not_rerun_solver(self) -> None:
        target = self.root / "temporarily-unavailable"
        target.write_bytes(b"not-a-directory")
        runtime = self.root / "runtime-retry"
        route = self._route(
            target,
            route_id="retry-route",
            machine_enabled=True,
            external_enabled=True,
            max_attempts=1,
        )
        engine = AutomationEngine(
            runtime,
            PROFILES,
            minimum_free_disk_mb=0,
            archive_route=route,
        )
        engine.submit(manifest("archive-retry"))
        self.assertEqual(engine.run_one()["state"], "SUCCEEDED")
        self.assertEqual(engine.drain_archives()[0]["state"], "FAILED")
        self.assertEqual(engine.database.latest_job_state("archive-retry"), "SUCCEEDED")
        self.assertEqual(len(engine.database.show_job("archive-retry")["attempts"]), 1)

        target.unlink()
        self.assertEqual(engine.retry_archives("archive-retry")[0]["state"], "RETRY")
        self.assertEqual(engine.drain_archives()[0]["state"], "SUCCEEDED")
        shown = engine.database.show_job("archive-retry")
        self.assertEqual(shown["state"], "SUCCEEDED")
        self.assertEqual(len(shown["attempts"]), 1)
        self.assertEqual(shown["archive_operations"][0]["state"], "SUCCEEDED")

    def test_changed_destination_requires_new_route_approval(self) -> None:
        first_target = self.root / "first-target"
        runtime = self.root / "runtime-fingerprint"
        blocked_route = self._route(
            first_target,
            route_id="stable-route",
            machine_enabled=False,
            external_enabled=True,
        )
        engine = AutomationEngine(runtime, PROFILES, minimum_free_disk_mb=0, archive_route=blocked_route)
        engine.submit(manifest("archive-fingerprint"))
        engine.run_one()
        self.assertEqual(engine.drain_archives()[0]["state"], "BLOCKED")

        changed_target = self.root / "changed-target"
        changed_route = self._route(
            changed_target,
            route_id="stable-route",
            machine_enabled=True,
            external_enabled=True,
        )
        restarted = AutomationEngine(runtime, PROFILES, minimum_free_disk_mb=0, archive_route=changed_route)
        restarted.retry_archives("archive-fingerprint")
        result = restarted.drain_archives()[0]
        self.assertEqual(result["state"], "BLOCKED")
        self.assertFalse(changed_target.exists())

    def test_interrupted_after_copy_reconciles_to_same_blob(self) -> None:
        target = self.root / "interrupted-target"
        route = self._route(
            target,
            route_id="interrupted-route",
            machine_enabled=True,
            external_enabled=True,
        )
        engine = AutomationEngine(
            self.root / "runtime-interrupted",
            PROFILES,
            minimum_free_disk_mb=0,
            archive_route=route,
        )
        engine.submit(manifest("archive-interrupted"))
        engine.run_one()
        claimed = engine.database.claim_archive_operations(route.route_id)[0]
        first = NasArtifactStorage(target, external_enabled=True).publish_file(
            Path(claimed["source_path"]), claimed["logical_name"]
        )
        self.assertEqual(engine.database.reconcile_archives(stale_after_sec=0), 1)
        self.assertEqual(engine.drain_archives()[0]["state"], "SUCCEEDED")
        operation = engine.database.list_archive_operations("archive-interrupted")[0]
        self.assertEqual(Path(operation["archive_path"]), first.path)
        self.assertEqual(operation["archive_sha256"], first.sha256)
        self.assertEqual(
            [transition["to_state"] for transition in operation["transitions"]],
            ["PENDING", "EXECUTING", "RETRY", "EXECUTING", "SUCCEEDED"],
        )

        connection = sqlite3.connect(engine.database.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE archive_operations SET route_id='changed' WHERE operation_id=?",
                    (operation["operation_id"],),
                )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
