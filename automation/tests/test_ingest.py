from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mecar_automation.engine import AutomationEngine
from mecar_automation.ingest import HotFolder

from .support import PROFILES, manifest


class HotFolderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.engine = AutomationEngine(self.root / "runtime", PROFILES, minimum_free_disk_mb=0)
        self.folder = HotFolder(self.root / "hot", self.engine.submit, stable_seconds=0, probe_seconds=0)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _drop(self, value: dict, name: str = "submission.json") -> None:
        path = self.folder.incoming / name
        path.write_text(json.dumps(value), encoding="utf-8")
        Path(str(path) + ".ready").write_bytes(b"")

    def test_ready_intake_and_duplicate_dedupe(self) -> None:
        value = manifest("ingest-dedupe")
        self._drop(value)
        first = self.folder.scan()
        self.assertEqual(first[0].disposition, "ACCEPTED")
        self._drop(value)
        second = self.folder.scan()
        self.assertEqual(second[0].disposition, "DUPLICATE")
        self.assertEqual(len(self.engine.database.list_jobs()), 1)

    def test_same_id_different_hash_is_quarantined(self) -> None:
        first = manifest("ingest-conflict")
        self._drop(first)
        self.folder.scan()
        second = manifest("ingest-conflict", timeout=3)
        self._drop(second)
        result = self.folder.scan()[0]
        self.assertEqual(result.disposition, "QUARANTINED")
        self.assertEqual(result.code, "SUBMISSION_ID_CONFLICT")
        self.assertEqual(len(list(self.folder.quarantine.glob("*/receipt.json"))), 1)

    def test_invalid_manifest_and_orphan_marker_are_quarantined(self) -> None:
        invalid = manifest("bad/id")
        self._drop(invalid, "invalid.json")
        orphan = self.folder.incoming / "orphan.json.ready"
        orphan.write_bytes(b"")
        results = self.folder.scan()
        self.assertEqual({item.code for item in results}, {"VALIDATION_ERROR", "READY_WITHOUT_MANIFEST"})

    def test_recent_file_is_deferred(self) -> None:
        folder = HotFolder(self.root / "slow", self.engine.submit, stable_seconds=60, probe_seconds=0)
        path = folder.incoming / "recent.json"
        path.write_text(json.dumps(manifest("recent")), encoding="utf-8")
        Path(str(path) + ".ready").write_bytes(b"")
        result = folder.scan()[0]
        self.assertEqual(result.disposition, "DEFERRED")
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()

