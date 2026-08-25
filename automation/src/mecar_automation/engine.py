from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from .adapters import default_adapters
from .artifacts import ArchiveDrainer, ArchiveRoute, ArtifactPublisher, archive_rollup
from .db import QueueDatabase, SubmitResult
from .errors import AutomationError, ResourceUnavailable, ValidationError
from .ingest import HotFolder
from .supervisor import ProcessSupervisor, ResourceCapacity, ResourceGate, SingletonFileLock, process_is_alive
from .util import atomic_write_json, canonical_json_bytes, sha256_bytes, utc_now
from .validation import ProfileRegistry, manifest_hash, validate_manifest
from . import __version__


class AutomationEngine:
    def __init__(
        self,
        runtime_root: Path,
        profiles_root: Path,
        *,
        external_execution_enabled: bool = False,
        capacity: ResourceCapacity | None = None,
        minimum_free_disk_mb: int = 64,
        notification_policy_version: str = "1",
        artifact_root: Path | None = None,
        archive_route: ArchiveRoute | None = None,
    ):
        self.runtime_root = runtime_root.resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.work_root = self.runtime_root / "work"
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.database = QueueDatabase(self.runtime_root / "state" / "automation.sqlite3")
        self.dispatcher_lock = SingletonFileLock(self.runtime_root / "state" / "dispatcher.lock")
        self.profiles = ProfileRegistry(profiles_root)
        self.adapters = default_adapters()
        self.external_execution_enabled = external_execution_enabled
        self.notification_policy_version = notification_policy_version
        self.archive_route = archive_route
        self.publisher = ArtifactPublisher(
            self.database,
            artifact_root or self.runtime_root / "artifacts",
            archive_route=archive_route,
        )
        self.archive_drainer = ArchiveDrainer(self.database, archive_route) if archive_route else None
        self.supervisor = ProcessSupervisor(
            ResourceGate(capacity or ResourceCapacity()), minimum_free_disk_mb=minimum_free_disk_mb
        )
        self.hotfolder = HotFolder(self.runtime_root / "hotfolder", self.submit)

    def submit(self, raw_manifest: dict[str, Any]) -> SubmitResult:
        manifest = validate_manifest(raw_manifest)
        profile = self.profiles.resolve(manifest["profile"]["id"], manifest["profile"]["version"])
        if profile["adapter"] != manifest["adapter"]:
            raise ValidationError("Manifest adapter does not match the selected profile")
        if not profile["enabled"]:
            raise ValidationError("Selected profile is not enabled")
        if manifest["adapter"] in {"mapdl_v211", "fluent_v211"} and manifest["timeout_sec"] > float(
            profile["settings"]["max_timeout_sec"]
        ):
            raise ValidationError("Manifest timeout exceeds the approved external profile ceiling")
        profile_sha256 = sha256_bytes(canonical_json_bytes(profile))
        return self.database.create_job(manifest, manifest_hash(manifest), profile, profile_sha256)

    def run_one(self) -> dict[str, Any] | None:
        claimed = self.database.claim_next(self.work_root)
        if claimed is None:
            return None
        manifest = claimed.manifest
        claimed.workdir.mkdir(parents=True, exist_ok=False)
        snapshot = claimed.workdir / "manifest.snapshot.json"
        atomic_write_json(snapshot, manifest)
        process = None
        outcome = None
        summary_path = claimed.workdir / "summary.json"
        try:
            profile = claimed.profile
            if not profile or not claimed.profile_hash:
                raise ValidationError("Immutable profile snapshot is missing from this legacy job")
            if profile["adapter"] != manifest["adapter"] or not profile["enabled"]:
                raise ValidationError("Stored profile snapshot is incompatible or disabled")
            adapter = self.adapters[manifest["adapter"]]
            profile_snapshot = claimed.workdir / "profile.snapshot.json"
            atomic_write_json(profile_snapshot, profile)
            profile_sha256 = sha256_bytes(canonical_json_bytes(profile))
            if profile_sha256 != claimed.profile_hash:
                raise ValidationError("Stored profile snapshot checksum mismatch")
            prepared = adapter.prepare(
                manifest,
                profile,
                claimed.workdir,
                external_execution_enabled=self.external_execution_enabled,
            )
            process = self.supervisor.run(
                prepared,
                claimed.workdir,
                timeout_sec=float(manifest["timeout_sec"]),
                resources=profile.get("resources", manifest["resources"]),
                cancel_check=lambda: self.database.cancel_requested(claimed.job_id),
                on_started=lambda pid: self.database.record_attempt_pid(claimed.attempt_id, pid),
                adapter_settings=profile.get("settings", {}),
            )
            outcome = adapter.evaluate(claimed.workdir, process)
            if process.cancelled:
                attempt_state, job_state, reason = "CANCELLED", "CANCELLED", "PROCESS_CANCELLED"
            elif process.timed_out:
                attempt_state, job_state, reason = "TIMED_OUT", "TIMED_OUT", "PROCESS_TIMEOUT"
            elif outcome.succeeded:
                attempt_state, job_state, reason = "SUCCEEDED", "SUCCEEDED", outcome.reason_code
            else:
                attempt_state, job_state, reason = "FAILED", "FAILED", outcome.reason_code
            summary = {
                "schema_version": "1.0.0",
                "job_id": claimed.job_id,
                "attempt_id": claimed.attempt_id,
                "attempt_no": claimed.attempt_no,
                "adapter": manifest["adapter"],
                "profile_sha256": profile_sha256,
                "job_state": job_state,
                "reason_code": reason,
                "metrics": outcome.metrics,
                "process": {
                    "exit_code": process.exit_code,
                    "timed_out": process.timed_out,
                    "cancelled": process.cancelled,
                    "duration_sec": process.duration_sec,
                },
                "resources": profile.get("resources", manifest["resources"]),
                "completed_at": utc_now(),
            }
            atomic_write_json(summary_path, summary)
            provenance_base = {
                "manifest_sha256": manifest_hash(manifest),
                "profile_id": manifest["profile"]["id"],
                "profile_version": manifest["profile"]["version"],
                "profile_sha256": profile_sha256,
                "adapter": manifest["adapter"],
                "reason_code": reason,
                "automation_version": __version__,
                "python_version": platform.python_version(),
            }
            self.publisher.publish(
                job_id=claimed.job_id,
                attempt_id=claimed.attempt_id,
                role="manifest_snapshot",
                source=snapshot,
                provenance={**provenance_base, "source_role": "manifest_snapshot"},
            )
            self.publisher.publish(
                job_id=claimed.job_id,
                attempt_id=claimed.attempt_id,
                role="profile_snapshot",
                source=profile_snapshot,
                provenance={**provenance_base, "source_role": "profile_snapshot"},
            )
            published_paths: set[Path] = set()
            for role, path in outcome.artifacts:
                resolved = path.resolve()
                if resolved in published_paths:
                    continue
                published_paths.add(resolved)
                self.publisher.publish(
                    job_id=claimed.job_id,
                    attempt_id=claimed.attempt_id,
                    role=role,
                    source=path,
                    provenance={**provenance_base, "source_role": role},
                )
            summary_artifact = self.publisher.publish(
                job_id=claimed.job_id,
                attempt_id=claimed.attempt_id,
                role="summary_report",
                source=summary_path,
                provenance={**provenance_base, "source_role": "summary_report"},
            )
            recipients = manifest.get("notification", {}).get("recipients", [])
            notification = None
            if recipients:
                notification = {
                    "policy_version": self.notification_policy_version,
                    "to": recipients,
                    "subject": f"MECar analysis {claimed.job_id}: {job_state}",
                    "text": (
                        f"Job {claimed.job_id} completed with state {job_state}. "
                        f"Reason: {reason}. Summary SHA-256: {summary_artifact['sha256']}."
                    ),
                }
            self.database.finish_attempt(
                claimed.attempt_id,
                attempt_state,
                job_state,
                reason,
                exit_code=process.exit_code,
                details={
                    "attempt_id": claimed.attempt_id,
                    "reason_code": reason,
                    "summary_sha256": summary_artifact["sha256"],
                },
                notification_payload=notification,
            )
        except ResourceUnavailable as exc:
            diagnostic = {
                "schema_version": "1.0.0",
                "job_id": claimed.job_id,
                "attempt_id": claimed.attempt_id,
                "job_state": "WAITING_RESOURCE",
                "reason_code": exc.code,
                "diagnostic_class": "SCHEDULING_RESOURCE",
                "recorded_at": utc_now(),
            }
            atomic_write_json(claimed.workdir / "resource-wait.json", diagnostic)
            self.database.defer_attempt_for_resources(
                claimed.attempt_id,
                exc.code,
                {
                    "attempt_id": claimed.attempt_id,
                    "reason_code": exc.code,
                    "diagnostic_class": "SCHEDULING_RESOURCE",
                },
            )
        except Exception as exc:
            code = exc.code if isinstance(exc, AutomationError) else "INTERNAL_ERROR"
            diagnostic = {
                "schema_version": "1.0.0",
                "job_id": claimed.job_id,
                "attempt_id": claimed.attempt_id,
                "job_state": "FAILED",
                "reason_code": code,
                "error_type": type(exc).__name__,
                "recorded_at": utc_now(),
            }
            atomic_write_json(summary_path, diagnostic)
            try:
                self.publisher.publish(
                    job_id=claimed.job_id,
                    attempt_id=claimed.attempt_id,
                    role="failure_record",
                    source=summary_path,
                    provenance={
                        "manifest_sha256": sha256_bytes(canonical_json_bytes(manifest)),
                        "adapter": manifest.get("adapter"),
                        "reason_code": code,
                    },
                )
            finally:
                self.database.finish_attempt(
                    claimed.attempt_id,
                    "FAILED",
                    "FAILED",
                    code,
                    exit_code=process.exit_code if process else None,
                    details={"attempt_id": claimed.attempt_id, "reason_code": code},
                )
        return self.database.show_job(claimed.job_id)

    def drain_jobs(self, max_jobs: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        while len(results) < max_jobs:
            result = self.run_one()
            if result is None:
                break
            results.append(result)
        return results

    def reconcile(self, max_attempts: int = 2) -> list[dict[str, Any]]:
        return self.database.reconcile_stale(process_is_alive, max_attempts=max_attempts)

    def reconcile_archives(self, stale_after_sec: float = 300.0) -> int:
        return self.database.reconcile_archives(stale_after_sec=stale_after_sec)

    def drain_archives(self, max_operations: int = 100) -> list[dict[str, Any]]:
        if self.archive_drainer is None:
            return []
        return self.archive_drainer.drain(limit=max_operations)

    def retry_archives(self, job_id: str | None = None) -> list[dict[str, Any]]:
        if self.archive_route is None:
            raise ValidationError("No archive route is configured; pass the approved app config")
        return self.database.retry_archive_operations(
            job_id=job_id,
            route_id=self.archive_route.route_id,
        )

    def verify(self, job_id: str | None = None) -> dict[str, Any]:
        artifacts = self.publisher.verify(job_id)
        archive_operations = self.database.list_archive_operations(job_id)
        return {
            "database": self.database.health(),
            "artifacts": artifacts,
            "archive_operations": archive_operations,
            "archive_status": archive_rollup(archive_operations),
            "valid": all(item["valid"] for item in artifacts),
        }
