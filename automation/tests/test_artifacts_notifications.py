from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path

from mecar_automation.artifacts import NasArtifactStorage
from mecar_automation.engine import AutomationEngine
from mecar_automation.errors import ExternalExecutionDisabled, ValidationError
from mecar_automation.notifications import FakeSender, OutboxDrainer, RecipientPolicy, SmtpSender

from .support import PROFILES, manifest


class ArtifactAndNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_staged_storage_and_corruption_detection(self) -> None:
        engine = AutomationEngine(self.root / "runtime", PROFILES, minimum_free_disk_mb=0)
        engine.submit(manifest("corruption"))
        engine.run_one()
        before = engine.verify("corruption")
        self.assertTrue(before["valid"])
        row = engine.database.list_artifacts("corruption")[0]
        path = Path(row["path"])
        path.chmod(stat.S_IWRITE | stat.S_IREAD)
        path.write_bytes(b"corrupt")
        after = engine.verify("corruption")
        self.assertFalse(after["valid"])
        self.assertTrue(any(not item["valid"] for item in after["artifacts"]))

    def test_remote_storage_requires_explicit_enablement(self) -> None:
        source = self.root / "source.bin"
        source.write_bytes(b"payload")
        blocked = NasArtifactStorage(self.root / "nas", external_enabled=False)
        with self.assertRaises(ExternalExecutionDisabled):
            blocked.publish_file(source)
        enabled = NasArtifactStorage(self.root / "fake-nas", external_enabled=True)
        blob = enabled.publish_file(source)
        self.assertTrue(enabled.verify(blob))

    def test_transactional_outbox_fake_sender(self) -> None:
        engine = AutomationEngine(self.root / "outbox", PROFILES, minimum_free_disk_mb=0)
        engine.submit(manifest("mail", recipients=["member@example.com"]))
        engine.run_one()
        self.assertEqual(len(engine.database.pending_outbox()), 1)
        sender = FakeSender()
        policy = RecipientPolicy(allowed_domains=frozenset({"example.com"}))
        results = OutboxDrainer(engine.database, sender, policy).drain()
        self.assertEqual(results[0]["state"], "SENT")
        self.assertEqual(len(sender.sent), 1)
        self.assertEqual(engine.database.pending_outbox(), [])

    def test_recipient_policy_is_rechecked_before_send(self) -> None:
        engine = AutomationEngine(self.root / "policy", PROFILES, minimum_free_disk_mb=0)
        engine.submit(manifest("revoked", recipients=["former@example.com"]))
        engine.run_one()
        sender = FakeSender()
        result = OutboxDrainer(engine.database, sender, RecipientPolicy()).drain()[0]
        self.assertEqual(result["state"], "POLICY_REVOKED")
        self.assertEqual(sender.sent, [])

    def test_transient_send_remains_pending(self) -> None:
        engine = AutomationEngine(self.root / "retry-mail", PROFILES, minimum_free_disk_mb=0)
        engine.submit(manifest("mail-retry", recipients=["member@example.com"]))
        engine.run_one()
        policy = RecipientPolicy(allowed_domains=frozenset({"example.com"}))
        result = OutboxDrainer(engine.database, FakeSender("transient"), policy).drain()[0]
        self.assertEqual(result["state"], "RETRY")
        self.assertEqual(len(engine.database.pending_outbox()), 1)

    def test_outbox_claim_is_exclusive_and_stale_claim_recovers(self) -> None:
        engine = AutomationEngine(self.root / "claim-mail", PROFILES, minimum_free_disk_mb=0)
        engine.submit(manifest("mail-claim", recipients=["member@example.com"]))
        engine.run_one()
        self.assertEqual(len(engine.database.claim_outbox()), 1)
        self.assertEqual(engine.database.claim_outbox(), [])
        self.assertEqual(engine.database.reconcile_outbox(stale_after_sec=0), 1)
        self.assertEqual(len(engine.database.pending_outbox()), 1)

    def test_smtp_requires_tls_references_and_explicit_enable(self) -> None:
        with self.assertRaises(ValidationError):
            SmtpSender(
                {
                    "security": "none",
                    "username_ref": "plain-user",
                    "password": "secret",
                },
                lambda value: value,
            )


if __name__ == "__main__":
    unittest.main()
