from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

from .errors import InvalidTransition, SubmissionConflict
from .util import canonical_json_bytes, utc_now


JOB_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"QUEUED"},
    "QUEUED": {"RUNNING", "CANCELLED"},
    "RUNNING": {
        "SUCCEEDED", "FAILED", "TIMED_OUT", "CANCEL_REQUESTED", "CANCELLED", "QUEUED", "WAITING_RESOURCE"
    },
    "CANCEL_REQUESTED": {"SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"},
    "SUCCEEDED": set(),
    "FAILED": {"QUEUED"},
    "TIMED_OUT": {"QUEUED"},
    "CANCELLED": {"QUEUED"},
    "WAITING_RESOURCE": {"QUEUED", "CANCELLED"},
}

ATTEMPT_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"RUNNING"},
    "RUNNING": {"RUNNING", "SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED", "INTERRUPTED"},
    "SUCCEEDED": set(),
    "FAILED": set(),
    "TIMED_OUT": set(),
    "CANCELLED": set(),
    "INTERRUPTED": set(),
}

ARCHIVE_TRANSITIONS: dict[str | None, set[str]] = {
    None: {"PENDING"},
    "PENDING": {"EXECUTING"},
    "RETRY": {"EXECUTING"},
    "EXECUTING": {"SUCCEEDED", "RETRY", "FAILED", "BLOCKED"},
    "FAILED": {"RETRY"},
    "BLOCKED": {"RETRY"},
    "SUCCEEDED": set(),
}


@dataclass(frozen=True)
class SubmitResult:
    job_id: str
    disposition: str


@dataclass(frozen=True)
class ClaimedJob:
    job_id: str
    attempt_id: str
    attempt_no: int
    workdir: Path
    manifest: dict[str, Any]
    profile: dict[str, Any]
    profile_hash: str


class QueueDatabase:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )
            applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
            if 1 not in applied:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS submissions (
                        submission_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        submission_id TEXT NOT NULL,
                        manifest_hash TEXT NOT NULL,
                        profile_hash TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        UNIQUE(submission_id, manifest_hash)
                    );
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        submission_id TEXT NOT NULL UNIQUE,
                        manifest_hash TEXT NOT NULL,
                        manifest_json TEXT NOT NULL,
                        profile_hash TEXT NOT NULL,
                        profile_json TEXT NOT NULL,
                        profile_id TEXT NOT NULL,
                        profile_version TEXT NOT NULL,
                        adapter TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS job_transitions (
                        transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_id TEXT NOT NULL REFERENCES jobs(job_id),
                        from_state TEXT,
                        to_state TEXT NOT NULL,
                        reason_code TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS attempts (
                        attempt_id TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL REFERENCES jobs(job_id),
                        attempt_no INTEGER NOT NULL,
                        workdir TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(job_id, attempt_no)
                    );
                    CREATE TABLE IF NOT EXISTS attempt_transitions (
                        transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                        from_state TEXT,
                        to_state TEXT NOT NULL,
                        pid INTEGER,
                        exit_code INTEGER,
                        reason_code TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS events (
                        event_id TEXT PRIMARY KEY,
                        job_id TEXT REFERENCES jobs(job_id),
                        event_type TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS artifacts (
                        artifact_id TEXT PRIMARY KEY,
                        job_id TEXT NOT NULL REFERENCES jobs(job_id),
                        attempt_id TEXT REFERENCES attempts(attempt_id),
                        role TEXT NOT NULL,
                        path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        provenance_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS outbox_messages (
                        message_id TEXT PRIMARY KEY,
                        dedupe_key TEXT NOT NULL UNIQUE,
                        job_id TEXT REFERENCES jobs(job_id),
                        kind TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        policy_version TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS outbox_deliveries (
                        delivery_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT NOT NULL REFERENCES outbox_messages(message_id),
                        attempt_no INTEGER NOT NULL,
                        state TEXT NOT NULL,
                        provider_receipt TEXT,
                        error_code TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE(message_id, attempt_no)
                    );
                    CREATE TABLE IF NOT EXISTS system_transitions (
                        transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        setting_key TEXT NOT NULL,
                        from_state TEXT,
                        to_state TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        occurred_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_job_transitions_latest ON job_transitions(job_id, transition_id DESC);
                    CREATE INDEX IF NOT EXISTS idx_attempt_transitions_latest ON attempt_transitions(attempt_id, transition_id DESC);
                    CREATE INDEX IF NOT EXISTS idx_attempts_job ON attempts(job_id, attempt_no DESC);
                    CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_outbox_deliveries_latest ON outbox_deliveries(message_id, delivery_id DESC);
                    """
                )
                protected = [
                    "submissions", "jobs", "job_transitions", "attempts", "attempt_transitions",
                    "events", "artifacts", "outbox_messages", "outbox_deliveries", "system_transitions",
                ]
                for table in protected:
                    connection.executescript(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table}
                        BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
                        CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
                        BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END;
                        """
                    )
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (1, utc_now())
                )
            if 2 not in applied:
                submission_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(submissions)").fetchall()
                }
                job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
                if "profile_hash" not in submission_columns:
                    connection.execute("ALTER TABLE submissions ADD COLUMN profile_hash TEXT")
                if "profile_hash" not in job_columns:
                    connection.execute("ALTER TABLE jobs ADD COLUMN profile_hash TEXT")
                if "profile_json" not in job_columns:
                    connection.execute("ALTER TABLE jobs ADD COLUMN profile_json TEXT")
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (2, utc_now())
                )
            if 3 not in applied:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS archive_operations (
                        operation_id TEXT PRIMARY KEY,
                        dedupe_key TEXT NOT NULL UNIQUE,
                        artifact_id TEXT NOT NULL REFERENCES artifacts(artifact_id),
                        job_id TEXT NOT NULL REFERENCES jobs(job_id),
                        route_id TEXT NOT NULL,
                        route_fingerprint TEXT NOT NULL,
                        logical_name TEXT NOT NULL,
                        expected_sha256 TEXT NOT NULL,
                        expected_size_bytes INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS archive_transitions (
                        transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        operation_id TEXT NOT NULL REFERENCES archive_operations(operation_id),
                        from_state TEXT,
                        to_state TEXT NOT NULL,
                        attempt_no INTEGER NOT NULL,
                        archive_path TEXT,
                        archive_sha256 TEXT,
                        archive_size_bytes INTEGER,
                        reason_code TEXT NOT NULL,
                        details_json TEXT NOT NULL,
                        occurred_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_archive_operations_job
                        ON archive_operations(job_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_archive_operations_route
                        ON archive_operations(route_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_archive_transitions_latest
                        ON archive_transitions(operation_id, transition_id DESC);
                    CREATE TRIGGER IF NOT EXISTS archive_operations_no_update
                        BEFORE UPDATE ON archive_operations
                        BEGIN SELECT RAISE(ABORT, 'archive_operations is append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS archive_operations_no_delete
                        BEFORE DELETE ON archive_operations
                        BEGIN SELECT RAISE(ABORT, 'archive_operations is append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS archive_transitions_no_update
                        BEFORE UPDATE ON archive_transitions
                        BEGIN SELECT RAISE(ABORT, 'archive_transitions is append-only'); END;
                    CREATE TRIGGER IF NOT EXISTS archive_transitions_no_delete
                        BEFORE DELETE ON archive_transitions
                        BEGIN SELECT RAISE(ABORT, 'archive_transitions is append-only'); END;
                    """
                )
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (3, utc_now())
                )
            connection.commit()

    @staticmethod
    def _json(value: Any) -> str:
        return canonical_json_bytes(value).decode("utf-8")

    @staticmethod
    def _latest_job_state(connection: sqlite3.Connection, job_id: str) -> str | None:
        row = connection.execute(
            "SELECT to_state FROM job_transitions WHERE job_id=? ORDER BY transition_id DESC LIMIT 1", (job_id,)
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _latest_attempt_state(connection: sqlite3.Connection, attempt_id: str) -> str | None:
        row = connection.execute(
            "SELECT to_state FROM attempt_transitions WHERE attempt_id=? ORDER BY transition_id DESC LIMIT 1",
            (attempt_id,),
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _latest_archive_state(connection: sqlite3.Connection, operation_id: str) -> str | None:
        row = connection.execute(
            "SELECT to_state FROM archive_transitions WHERE operation_id=? "
            "ORDER BY transition_id DESC LIMIT 1",
            (operation_id,),
        ).fetchone()
        return row[0] if row else None

    def _transition_job(
        self,
        connection: sqlite3.Connection,
        job_id: str,
        to_state: str,
        reason_code: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        current = self._latest_job_state(connection, job_id)
        if to_state not in JOB_TRANSITIONS.get(current, set()):
            raise InvalidTransition(f"Job {job_id}: {current} -> {to_state}")
        connection.execute(
            "INSERT INTO job_transitions(job_id, from_state, to_state, reason_code, details_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job_id, current, to_state, reason_code, self._json(details or {}), utc_now()),
        )

    def _transition_attempt(
        self,
        connection: sqlite3.Connection,
        attempt_id: str,
        to_state: str,
        reason_code: str,
        *,
        pid: int | None = None,
        exit_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        current = self._latest_attempt_state(connection, attempt_id)
        if to_state not in ATTEMPT_TRANSITIONS.get(current, set()):
            raise InvalidTransition(f"Attempt {attempt_id}: {current} -> {to_state}")
        connection.execute(
            "INSERT INTO attempt_transitions(attempt_id, from_state, to_state, pid, exit_code, reason_code, "
            "details_json, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (attempt_id, current, to_state, pid, exit_code, reason_code, self._json(details or {}), utc_now()),
        )

    def _transition_archive(
        self,
        connection: sqlite3.Connection,
        operation_id: str,
        to_state: str,
        reason_code: str,
        *,
        attempt_no: int | None = None,
        archive_path: str | None = None,
        archive_sha256: str | None = None,
        archive_size_bytes: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        current = self._latest_archive_state(connection, operation_id)
        if to_state not in ARCHIVE_TRANSITIONS.get(current, set()):
            raise InvalidTransition(f"Archive operation {operation_id}: {current} -> {to_state}")
        if attempt_no is None:
            row = connection.execute(
                "SELECT attempt_no FROM archive_transitions WHERE operation_id=? "
                "ORDER BY transition_id DESC LIMIT 1",
                (operation_id,),
            ).fetchone()
            attempt_no = int(row[0]) if row else 0
        connection.execute(
            "INSERT INTO archive_transitions(operation_id, from_state, to_state, attempt_no, archive_path, "
            "archive_sha256, archive_size_bytes, reason_code, details_json, occurred_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                current,
                to_state,
                attempt_no,
                archive_path,
                archive_sha256,
                archive_size_bytes,
                reason_code,
                self._json(details or {}),
                utc_now(),
            ),
        )

    def _event(
        self, connection: sqlite3.Connection, job_id: str | None, event_type: str, payload: dict[str, Any]
    ) -> str:
        event_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO events(event_id, job_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, job_id, event_type, self._json(payload), utc_now()),
        )
        return event_id

    def create_job(
        self,
        manifest: dict[str, Any],
        manifest_hash: str,
        profile: dict[str, Any],
        profile_hash: str,
    ) -> SubmitResult:
        submission_id = manifest["submission_id"]
        with self.transaction() as connection:
            prior = connection.execute(
                "SELECT manifest_hash, profile_hash FROM submissions WHERE submission_id=? ORDER BY submission_row_id",
                (submission_id,),
            ).fetchall()
            if prior:
                if any(row[0] == manifest_hash and row[1] == profile_hash for row in prior):
                    return SubmitResult(submission_id, "DUPLICATE")
                raise SubmissionConflict(
                    f"submission_id {submission_id!r} already has a different manifest/profile identity"
                )
            payload = self._json(manifest)
            now = utc_now()
            connection.execute(
                "INSERT INTO submissions(submission_id, manifest_hash, profile_hash, manifest_json, received_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (submission_id, manifest_hash, profile_hash, payload, now),
            )
            connection.execute(
                "INSERT INTO jobs(job_id, submission_id, manifest_hash, manifest_json, profile_hash, profile_json, "
                "profile_id, profile_version, adapter, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    submission_id,
                    submission_id,
                    manifest_hash,
                    payload,
                    profile_hash,
                    self._json(profile),
                    manifest["profile"]["id"],
                    manifest["profile"]["version"],
                    manifest["adapter"],
                    now,
                ),
            )
            self._transition_job(connection, submission_id, "QUEUED", "SUBMITTED")
            self._event(
                connection,
                submission_id,
                "analysis.job.queued",
                {"manifest_sha256": manifest_hash, "profile_sha256": profile_hash},
            )
            return SubmitResult(submission_id, "ACCEPTED")

    def is_paused(self) -> bool:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT to_state FROM system_transitions WHERE setting_key='dispatcher' "
                "ORDER BY transition_id DESC LIMIT 1"
            ).fetchone()
            return bool(row and row[0] == "PAUSED")

    def set_paused(self, paused: bool, actor: str = "cli") -> str:
        target = "PAUSED" if paused else "RUNNING"
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT to_state FROM system_transitions WHERE setting_key='dispatcher' "
                "ORDER BY transition_id DESC LIMIT 1"
            ).fetchone()
            current = row[0] if row else "RUNNING"
            if current != target:
                connection.execute(
                    "INSERT INTO system_transitions(setting_key, from_state, to_state, actor, occurred_at) "
                    "VALUES ('dispatcher', ?, ?, ?, ?)",
                    (current, target, actor, utc_now()),
                )
            return target

    def claim_next(self, work_root: Path) -> ClaimedJob | None:
        if self.is_paused():
            return None
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT j.* FROM jobs j WHERE "
                "(SELECT to_state FROM job_transitions t WHERE t.job_id=j.job_id "
                " ORDER BY transition_id DESC LIMIT 1)='QUEUED' ORDER BY j.created_at, j.job_id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            attempt_no = connection.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM attempts WHERE job_id=?", (row["job_id"],)
            ).fetchone()[0]
            attempt_id = str(uuid.uuid4())
            workdir = work_root / row["job_id"] / f"attempt-{attempt_no:04d}-{attempt_id[:8]}"
            connection.execute(
                "INSERT INTO attempts(attempt_id, job_id, attempt_no, workdir, created_at) VALUES (?, ?, ?, ?, ?)",
                (attempt_id, row["job_id"], attempt_no, str(workdir), utc_now()),
            )
            self._transition_attempt(connection, attempt_id, "RUNNING", "CLAIMED")
            self._transition_job(connection, row["job_id"], "RUNNING", "ATTEMPT_STARTED", {"attempt_id": attempt_id})
            self._event(
                connection,
                row["job_id"],
                "analysis.attempt.started",
                {"attempt_id": attempt_id, "attempt_no": attempt_no},
            )
            return ClaimedJob(
                row["job_id"],
                attempt_id,
                attempt_no,
                workdir,
                json.loads(row["manifest_json"]),
                json.loads(row["profile_json"]) if row["profile_json"] else {},
                row["profile_hash"] or "",
            )

    def record_attempt_pid(self, attempt_id: str, pid: int) -> None:
        with self.transaction() as connection:
            self._transition_attempt(connection, attempt_id, "RUNNING", "PROCESS_STARTED", pid=pid)

    def finish_attempt(
        self,
        attempt_id: str,
        attempt_state: str,
        job_state: str,
        reason_code: str,
        *,
        exit_code: int | None,
        details: dict[str, Any],
        notification_payload: dict[str, Any] | None = None,
    ) -> None:
        with self.transaction() as connection:
            attempt = connection.execute("SELECT job_id FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise KeyError(attempt_id)
            job_id = attempt["job_id"]
            self._transition_attempt(
                connection, attempt_id, attempt_state, reason_code, exit_code=exit_code, details=details
            )
            self._transition_job(connection, job_id, job_state, reason_code, details)
            event_type = {
                "SUCCEEDED": "analysis.job.succeeded",
                "FAILED": "analysis.job.failed",
                "TIMED_OUT": "analysis.job.timed_out",
                "CANCELLED": "analysis.job.cancelled",
            }[job_state]
            event_id = self._event(connection, job_id, event_type, details)
            if notification_payload:
                message_id = str(uuid.uuid4())
                connection.execute(
                    "INSERT INTO outbox_messages(message_id, dedupe_key, job_id, kind, payload_json, policy_version, "
                    "created_at) VALUES (?, ?, ?, 'smtp', ?, ?, ?)",
                    (
                        message_id,
                        f"{attempt_id}:{event_type}:smtp",
                        job_id,
                        self._json(notification_payload),
                        notification_payload.get("policy_version", "1"),
                        utc_now(),
                    ),
                )
                self._event(
                    connection,
                    job_id,
                    "integration.smtp.queued",
                    {"message_id": message_id, "source_event_id": event_id},
                )

    def defer_attempt_for_resources(
        self,
        attempt_id: str,
        reason_code: str,
        details: dict[str, Any],
    ) -> None:
        """End execution bookkeeping without recording an engineering failure."""
        with self.transaction() as connection:
            attempt = connection.execute("SELECT job_id FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise KeyError(attempt_id)
            job_id = attempt["job_id"]
            self._transition_attempt(
                connection,
                attempt_id,
                "INTERRUPTED",
                reason_code,
                details=details,
            )
            self._transition_job(connection, job_id, "WAITING_RESOURCE", reason_code, details)
            self._event(
                connection,
                job_id,
                "analysis.job.waiting_resource",
                {"attempt_id": attempt_id, "reason_code": reason_code},
            )

    def request_cancel(self, job_id: str, actor: str = "cli") -> str:
        with self.transaction() as connection:
            state = self._latest_job_state(connection, job_id)
            if state in {"QUEUED", "WAITING_RESOURCE"}:
                self._transition_job(connection, job_id, "CANCELLED", "CANCELLED_BEFORE_START", {"actor": actor})
                self._event(connection, job_id, "analysis.job.cancelled", {"actor": actor})
                return "CANCELLED"
            if state == "RUNNING":
                self._transition_job(connection, job_id, "CANCEL_REQUESTED", "CANCEL_REQUESTED", {"actor": actor})
                self._event(connection, job_id, "analysis.job.cancel_requested", {"actor": actor})
                return "CANCEL_REQUESTED"
            if state == "CANCEL_REQUESTED":
                return state
            raise InvalidTransition(f"Cannot cancel job {job_id} from {state}")

    def cancel_requested(self, job_id: str) -> bool:
        with self.connection() as connection:
            return self._latest_job_state(connection, job_id) == "CANCEL_REQUESTED"

    def retry(self, job_id: str, actor: str = "cli") -> str:
        with self.transaction() as connection:
            self._transition_job(connection, job_id, "QUEUED", "MANUAL_RETRY", {"actor": actor})
            self._event(connection, job_id, "analysis.job.requeued", {"actor": actor})
            return "QUEUED"

    def latest_job_state(self, job_id: str) -> str | None:
        with self.connection() as connection:
            return self._latest_job_state(connection, job_id)

    def reconcile_stale(
        self,
        is_alive: Callable[[int], bool],
        *,
        max_attempts: int = 2,
    ) -> list[dict[str, Any]]:
        reconciled: list[dict[str, Any]] = []
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT a.*, (SELECT pid FROM attempt_transitions t WHERE t.attempt_id=a.attempt_id "
                "ORDER BY transition_id DESC LIMIT 1) AS pid, "
                "(SELECT to_state FROM attempt_transitions t WHERE t.attempt_id=a.attempt_id "
                "ORDER BY transition_id DESC LIMIT 1) AS attempt_state "
                "FROM attempts a"
            ).fetchall()
            for row in rows:
                if row["attempt_state"] != "RUNNING":
                    continue
                pid = row["pid"]
                if pid is not None and is_alive(int(pid)):
                    continue
                job_state = self._latest_job_state(connection, row["job_id"])
                if job_state not in {"RUNNING", "CANCEL_REQUESTED"}:
                    continue
                self._transition_attempt(
                    connection,
                    row["attempt_id"],
                    "INTERRUPTED",
                    "STALE_PROCESS",
                    pid=pid,
                )
                if job_state == "CANCEL_REQUESTED":
                    target = "CANCELLED"
                elif int(row["attempt_no"]) < max_attempts:
                    target = "QUEUED"
                else:
                    target = "FAILED"
                self._transition_job(
                    connection,
                    row["job_id"],
                    target,
                    "STALE_PROCESS",
                    {"attempt_id": row["attempt_id"], "pid": pid},
                )
                self._event(
                    connection,
                    row["job_id"],
                    "analysis.attempt.reconciled",
                    {"attempt_id": row["attempt_id"], "target": target},
                )
                reconciled.append({"job_id": row["job_id"], "attempt_id": row["attempt_id"], "state": target})
        return reconciled

    def add_artifact(
        self,
        *,
        artifact_id: str,
        job_id: str,
        attempt_id: str | None,
        role: str,
        path: str,
        sha256: str,
        size_bytes: int,
        provenance: dict[str, Any],
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO artifacts(artifact_id, job_id, attempt_id, role, path, sha256, size_bytes, "
                "provenance_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    job_id,
                    attempt_id,
                    role,
                    path,
                    sha256,
                    size_bytes,
                    self._json(provenance),
                    utc_now(),
                ),
            )

    def list_artifacts(self, job_id: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as connection:
            if job_id:
                rows = connection.execute("SELECT * FROM artifacts WHERE job_id=? ORDER BY created_at", (job_id,))
            else:
                rows = connection.execute("SELECT * FROM artifacts ORDER BY created_at")
            return [dict(row) for row in rows]

    def create_archive_operation(
        self,
        *,
        artifact_id: str,
        route_id: str,
        route_fingerprint: str,
        logical_name: str,
    ) -> str:
        """Create one immutable archive intent per artifact and approved route identity."""
        dedupe_key = f"{route_id}:{artifact_id}"
        operation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mecar-archive:{dedupe_key}"))
        with self.transaction() as connection:
            artifact = connection.execute(
                "SELECT job_id, sha256, size_bytes FROM artifacts WHERE artifact_id=?", (artifact_id,)
            ).fetchone()
            if artifact is None:
                raise KeyError(artifact_id)
            inserted = connection.execute(
                "INSERT OR IGNORE INTO archive_operations(operation_id, dedupe_key, artifact_id, job_id, "
                "route_id, route_fingerprint, logical_name, expected_sha256, expected_size_bytes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    operation_id,
                    dedupe_key,
                    artifact_id,
                    artifact["job_id"],
                    route_id,
                    route_fingerprint,
                    logical_name,
                    artifact["sha256"],
                    artifact["size_bytes"],
                    utc_now(),
                ),
            ).rowcount
            if inserted:
                self._transition_archive(connection, operation_id, "PENDING", "ARCHIVE_QUEUED")
                self._event(
                    connection,
                    artifact["job_id"],
                    "integration.archive.queued",
                    {"operation_id": operation_id, "artifact_id": artifact_id, "route_id": route_id},
                )
            else:
                existing = connection.execute(
                    "SELECT route_fingerprint, logical_name, expected_sha256, expected_size_bytes "
                    "FROM archive_operations WHERE operation_id=?",
                    (operation_id,),
                ).fetchone()
                expected = (
                    route_fingerprint,
                    logical_name,
                    artifact["sha256"],
                    artifact["size_bytes"],
                )
                if existing is None or tuple(existing) != expected:
                    raise SubmissionConflict("Archive route identity conflicts with an existing immutable intent")
        return operation_id

    def list_archive_operations(self, job_id: str | None = None) -> list[dict[str, Any]]:
        with self.connection() as connection:
            where = "WHERE o.job_id=?" if job_id else ""
            parameters: tuple[Any, ...] = (job_id,) if job_id else ()
            rows = connection.execute(
                "SELECT o.*, a.role, a.path AS source_path, "
                "(SELECT t.to_state FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) AS state, "
                "(SELECT t.reason_code FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) AS reason_code, "
                "(SELECT t.attempt_no FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) AS attempt_no, "
                "(SELECT t.archive_path FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) AS archive_path, "
                "(SELECT t.archive_sha256 FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) AS archive_sha256, "
                "(SELECT t.archive_size_bytes FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) AS archive_size_bytes "
                f"FROM archive_operations o JOIN artifacts a ON a.artifact_id=o.artifact_id {where} "
                "ORDER BY o.created_at, o.operation_id",
                parameters,
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["transitions"] = [
                    dict(transition)
                    for transition in connection.execute(
                        "SELECT * FROM archive_transitions WHERE operation_id=? ORDER BY transition_id",
                        (item["operation_id"],),
                    )
                ]
                result.append(item)
            return result

    def claim_archive_operations(self, route_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Exclusively claim pending archive intents without touching analysis attempts."""
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT o.*, a.role, a.path AS source_path FROM archive_operations o "
                "JOIN artifacts a ON a.artifact_id=o.artifact_id "
                "WHERE o.route_id=? AND "
                "(SELECT t.to_state FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) IN ('PENDING','RETRY') "
                "ORDER BY o.created_at, o.operation_id LIMIT ?",
                (route_id, max(0, int(limit))),
            ).fetchall()
            claimed: list[dict[str, Any]] = []
            for row in rows:
                attempt_no = connection.execute(
                    "SELECT COUNT(*) + 1 FROM archive_transitions "
                    "WHERE operation_id=? AND to_state='EXECUTING'",
                    (row["operation_id"],),
                ).fetchone()[0]
                self._transition_archive(
                    connection,
                    row["operation_id"],
                    "EXECUTING",
                    "ARCHIVE_CLAIMED",
                    attempt_no=int(attempt_no),
                )
                item = dict(row)
                item["attempt_no"] = int(attempt_no)
                claimed.append(item)
            return claimed

    def record_archive_result(
        self,
        operation_id: str,
        state: str,
        reason_code: str,
        *,
        archive_path: str | None = None,
        archive_sha256: str | None = None,
        archive_size_bytes: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        if state not in {"SUCCEEDED", "RETRY", "FAILED", "BLOCKED"}:
            raise InvalidTransition(f"Invalid archive result state: {state}")
        with self.transaction() as connection:
            operation = connection.execute(
                "SELECT job_id, artifact_id, route_id FROM archive_operations WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            if operation is None:
                raise KeyError(operation_id)
            self._transition_archive(
                connection,
                operation_id,
                state,
                reason_code,
                archive_path=archive_path,
                archive_sha256=archive_sha256,
                archive_size_bytes=archive_size_bytes,
                details=details,
            )
            self._event(
                connection,
                operation["job_id"],
                f"integration.archive.{state.lower()}",
                {
                    "operation_id": operation_id,
                    "artifact_id": operation["artifact_id"],
                    "route_id": operation["route_id"],
                    "reason_code": reason_code,
                },
            )

    def retry_archive_operations(
        self,
        *,
        job_id: str | None = None,
        route_id: str | None = None,
        actor: str = "cli",
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if job_id:
            clauses.append("o.job_id=?")
            parameters.append(job_id)
        if route_id:
            clauses.append("o.route_id=?")
            parameters.append(route_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        retried: list[dict[str, Any]] = []
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT o.operation_id, o.job_id, o.artifact_id, o.route_id, "
                "(SELECT t.to_state FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                " ORDER BY t.transition_id DESC LIMIT 1) AS state "
                f"FROM archive_operations o {where} ORDER BY o.created_at, o.operation_id",
                tuple(parameters),
            ).fetchall()
            for row in rows:
                if row["state"] not in {"FAILED", "BLOCKED"}:
                    continue
                self._transition_archive(
                    connection,
                    row["operation_id"],
                    "RETRY",
                    "ARCHIVE_MANUAL_RETRY",
                    details={"actor": actor},
                )
                self._event(
                    connection,
                    row["job_id"],
                    "integration.archive.requeued",
                    {
                        "operation_id": row["operation_id"],
                        "artifact_id": row["artifact_id"],
                        "route_id": row["route_id"],
                        "actor": actor,
                    },
                )
                retried.append({"operation_id": row["operation_id"], "state": "RETRY"})
        return retried

    def reconcile_archives(self, stale_after_sec: float = 300.0) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=max(0.0, stale_after_sec))
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        reconciled = 0
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT o.operation_id, o.job_id FROM archive_operations o "
                "JOIN archive_transitions t ON t.transition_id=(SELECT t2.transition_id "
                "FROM archive_transitions t2 WHERE t2.operation_id=o.operation_id "
                "ORDER BY t2.transition_id DESC LIMIT 1) "
                "WHERE t.to_state='EXECUTING' AND t.occurred_at<=?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                self._transition_archive(
                    connection,
                    row["operation_id"],
                    "RETRY",
                    "ARCHIVE_STALE",
                )
                self._event(
                    connection,
                    row["job_id"],
                    "integration.archive.requeued",
                    {"operation_id": row["operation_id"], "reason_code": "ARCHIVE_STALE"},
                )
                reconciled += 1
        return reconciled

    def pending_archive_count(self) -> int:
        with self.connection() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM archive_operations o WHERE "
                    "(SELECT t.to_state FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                    " ORDER BY t.transition_id DESC LIMIT 1) IN ('PENDING','RETRY','EXECUTING')"
                ).fetchone()[0]
            )

    def pending_outbox(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT m.*, (SELECT state FROM outbox_deliveries d WHERE d.message_id=m.message_id "
                "ORDER BY delivery_id DESC LIMIT 1) AS latest_state FROM outbox_messages m "
                "WHERE COALESCE((SELECT state FROM outbox_deliveries d WHERE d.message_id=m.message_id "
                "ORDER BY delivery_id DESC LIMIT 1), 'PENDING') IN ('PENDING','RETRY') "
                "ORDER BY m.created_at LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                result.append(item)
            return result

    def claim_outbox(self, limit: int = 100) -> list[dict[str, Any]]:
        """Atomically appends EXECUTING leases so parallel drainers cannot send the same intent."""
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT m.*, (SELECT state FROM outbox_deliveries d WHERE d.message_id=m.message_id "
                "ORDER BY delivery_id DESC LIMIT 1) AS latest_state FROM outbox_messages m "
                "WHERE COALESCE((SELECT state FROM outbox_deliveries d WHERE d.message_id=m.message_id "
                "ORDER BY delivery_id DESC LIMIT 1), 'PENDING') IN ('PENDING','RETRY') "
                "ORDER BY m.created_at LIMIT ?",
                (limit,),
            ).fetchall()
            result: list[dict[str, Any]] = []
            for row in rows:
                attempt_no = connection.execute(
                    "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM outbox_deliveries WHERE message_id=?",
                    (row["message_id"],),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO outbox_deliveries(message_id, attempt_no, state, provider_receipt, error_code, "
                    "created_at) VALUES (?, ?, 'EXECUTING', NULL, NULL, ?)",
                    (row["message_id"], attempt_no, utc_now()),
                )
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                result.append(item)
            return result

    def reconcile_outbox(self, stale_after_sec: float = 300.0) -> int:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(seconds=max(0.0, stale_after_sec))
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        reconciled = 0
        with self.transaction() as connection:
            rows = connection.execute(
                "SELECT m.message_id, d.created_at FROM outbox_messages m JOIN outbox_deliveries d "
                "ON d.delivery_id=(SELECT d2.delivery_id FROM outbox_deliveries d2 "
                "WHERE d2.message_id=m.message_id ORDER BY d2.delivery_id DESC LIMIT 1) "
                "WHERE d.state='EXECUTING' AND d.created_at<=?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                attempt_no = connection.execute(
                    "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM outbox_deliveries WHERE message_id=?",
                    (row["message_id"],),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO outbox_deliveries(message_id, attempt_no, state, provider_receipt, error_code, "
                    "created_at) VALUES (?, ?, 'RETRY', NULL, 'OUTBOX_STALE', ?)",
                    (row["message_id"], attempt_no, utc_now()),
                )
                reconciled += 1
        return reconciled

    def record_outbox_delivery(
        self,
        message_id: str,
        state: str,
        *,
        receipt: str | None = None,
        error_code: str | None = None,
    ) -> None:
        with self.transaction() as connection:
            attempt_no = connection.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM outbox_deliveries WHERE message_id=?",
                (message_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO outbox_deliveries(message_id, attempt_no, state, provider_receipt, error_code, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (message_id, attempt_no, state, receipt, error_code, utc_now()),
            )

    def list_jobs(self) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT j.job_id, j.submission_id, j.adapter, j.profile_id, j.profile_version, j.created_at, "
                "(SELECT to_state FROM job_transitions t WHERE t.job_id=j.job_id "
                " ORDER BY transition_id DESC LIMIT 1) AS state FROM jobs j ORDER BY j.created_at, j.job_id"
            ).fetchall()
            return [dict(row) for row in rows]

    def show_job(self, job_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise KeyError(job_id)
            result = dict(job)
            result["manifest"] = json.loads(result.pop("manifest_json"))
            profile_json = result.pop("profile_json", None)
            result["profile_snapshot"] = json.loads(profile_json) if profile_json else None
            result["state"] = self._latest_job_state(connection, job_id)
            result["transitions"] = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM job_transitions WHERE job_id=? ORDER BY transition_id", (job_id,)
                )
            ]
            result["attempts"] = []
            for attempt in connection.execute(
                "SELECT * FROM attempts WHERE job_id=? ORDER BY attempt_no", (job_id,)
            ):
                item = dict(attempt)
                item["state"] = self._latest_attempt_state(connection, item["attempt_id"])
                result["attempts"].append(item)
            result["events"] = [
                dict(row)
                for row in connection.execute("SELECT * FROM events WHERE job_id=? ORDER BY created_at", (job_id,))
            ]
            result["artifacts"] = [
                dict(row)
                for row in connection.execute("SELECT * FROM artifacts WHERE job_id=? ORDER BY created_at", (job_id,))
            ]
            archive_rows = connection.execute(
                "SELECT o.*, (SELECT t.to_state FROM archive_transitions t "
                "WHERE t.operation_id=o.operation_id ORDER BY t.transition_id DESC LIMIT 1) AS state, "
                "(SELECT t.reason_code FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                "ORDER BY t.transition_id DESC LIMIT 1) AS reason_code, "
                "(SELECT t.attempt_no FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                "ORDER BY t.transition_id DESC LIMIT 1) AS attempt_no, "
                "(SELECT t.archive_path FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                "ORDER BY t.transition_id DESC LIMIT 1) AS archive_path, "
                "(SELECT t.archive_sha256 FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                "ORDER BY t.transition_id DESC LIMIT 1) AS archive_sha256 "
                "FROM archive_operations o WHERE o.job_id=? ORDER BY o.created_at, o.operation_id",
                (job_id,),
            ).fetchall()
            result["archive_operations"] = [dict(row) for row in archive_rows]
            return result

    def get_manifest(self, job_id: str) -> dict[str, Any]:
        with self.connection() as connection:
            row = connection.execute("SELECT manifest_json FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return json.loads(row[0])

    def operational_snapshot(self, recent_limit: int = 10) -> dict[str, Any]:
        limit = min(max(int(recent_limit), 1), 100)
        with self.connection() as connection:
            job_states = {
                row["state"]: int(row["count"])
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS count FROM (SELECT "
                    "(SELECT t.to_state FROM job_transitions t WHERE t.job_id=j.job_id "
                    " ORDER BY t.transition_id DESC LIMIT 1) AS state FROM jobs j) GROUP BY state"
                )
            }
            archive_states = {
                row["state"]: int(row["count"])
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS count FROM (SELECT "
                    "(SELECT t.to_state FROM archive_transitions t WHERE t.operation_id=o.operation_id "
                    " ORDER BY t.transition_id DESC LIMIT 1) AS state FROM archive_operations o) GROUP BY state"
                )
            }
            notification_states = {
                row["state"]: int(row["count"])
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS count FROM (SELECT COALESCE("
                    "(SELECT d.state FROM outbox_deliveries d WHERE d.message_id=m.message_id "
                    " ORDER BY d.delivery_id DESC LIMIT 1), 'PENDING') AS state FROM outbox_messages m) GROUP BY state"
                )
            }
            recent: list[dict[str, Any]] = [
                {
                    "source": "analysis",
                    "job_id": row["job_id"],
                    "state": row["to_state"],
                    "reason_code": row["reason_code"],
                    "occurred_at": row["occurred_at"],
                }
                for row in connection.execute(
                    "SELECT job_id, to_state, reason_code, occurred_at FROM job_transitions "
                    "WHERE to_state IN ('FAILED','TIMED_OUT','WAITING_RESOURCE') "
                    "ORDER BY transition_id DESC LIMIT ?",
                    (limit,),
                )
            ]
            recent.extend(
                {
                    "source": "archive",
                    "job_id": row["job_id"],
                    "state": row["to_state"],
                    "reason_code": row["reason_code"],
                    "occurred_at": row["occurred_at"],
                }
                for row in connection.execute(
                    "SELECT o.job_id, t.to_state, t.reason_code, t.occurred_at "
                    "FROM archive_transitions t JOIN archive_operations o ON o.operation_id=t.operation_id "
                    "WHERE t.to_state IN ('FAILED','BLOCKED','RETRY') "
                    "ORDER BY t.transition_id DESC LIMIT ?",
                    (limit,),
                )
            )
            recent.extend(
                {
                    "source": "notification",
                    "job_id": row["job_id"],
                    "state": row["state"],
                    "reason_code": row["error_code"],
                    "occurred_at": row["created_at"],
                }
                for row in connection.execute(
                    "SELECT m.job_id, d.state, d.error_code, d.created_at FROM outbox_deliveries d "
                    "JOIN outbox_messages m ON m.message_id=d.message_id "
                    "WHERE d.state IN ('RETRY','PERMANENT','POLICY_REVOKED') "
                    "ORDER BY d.delivery_id DESC LIMIT ?",
                    (limit,),
                )
            )
            recent.sort(key=lambda item: item["occurred_at"], reverse=True)
            return {
                "jobs": job_states,
                "archive": archive_states,
                "notifications": notification_states,
                "recent_errors": recent[:limit],
            }

    def health(self) -> dict[str, Any]:
        with self.connection() as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            migration = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            return {
                "database": str(self.path),
                "integrity": integrity,
                "schema_version": migration,
                "paused": self.is_paused(),
                "job_count": connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0],
                "pending_outbox": len(self.pending_outbox()),
                "pending_archive": self.pending_archive_count(),
            }
