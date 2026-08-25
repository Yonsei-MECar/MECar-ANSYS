from __future__ import annotations

import os
import json
import shutil
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import QueueDatabase
from .errors import ArtifactCorruption, ExternalExecutionDisabled, ValidationError
from .util import (
    atomic_write_json,
    canonical_json_bytes,
    require_safe_component,
    sha256_bytes,
    sha256_file,
    utc_now,
)


@dataclass(frozen=True)
class PublishedBlob:
    path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ArchiveRoute:
    """One approved optional NAS archive route layered after local immutable publication."""

    route_id: str
    root: Path
    roles: frozenset[str]
    machine_enabled: bool = False
    external_enabled: bool = False
    max_attempts: int = 3

    @property
    def enabled(self) -> bool:
        return self.machine_enabled and self.external_enabled

    @property
    def fingerprint(self) -> str:
        # Path normalization is lexical; constructing a route never probes a UNC endpoint.
        normalized_root = os.path.normcase(os.path.abspath(str(self.root)))
        return sha256_bytes(
            canonical_json_bytes(
                {"adapter": "nas", "route_id": self.route_id, "root": normalized_root}
            )
        )

    def includes(self, role: str) -> bool:
        return "*" in self.roles or role in self.roles

    @classmethod
    def from_config(
        cls,
        raw: dict[str, Any] | None,
        *,
        machine_enabled: bool,
    ) -> ArchiveRoute | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise ValidationError("artifacts.archive must be an object")
        adapter = raw.get("adapter", "disabled")
        if adapter == "disabled":
            return None
        if adapter != "nas":
            raise ValidationError("artifacts.archive.adapter must be disabled or nas")
        route_id = require_safe_component(raw.get("route_id"), "artifacts.archive.route_id")
        root_value = raw.get("root")
        if not isinstance(root_value, str) or not root_value.strip() or "\x00" in root_value:
            raise ValidationError("artifacts.archive.root must be a non-empty absolute path")
        root = Path(root_value)
        if not root.is_absolute():
            raise ValidationError("artifacts.archive.root must be absolute")
        raw_roles = raw.get("roles")
        if not isinstance(raw_roles, list) or not raw_roles:
            raise ValidationError("artifacts.archive.roles must be a non-empty array")
        roles = frozenset(require_safe_component(value, "artifacts.archive.roles[]") for value in raw_roles)
        max_attempts = raw.get("max_attempts", 3)
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 100:
            raise ValidationError("artifacts.archive.max_attempts must be an integer from 1 to 100")
        route_enabled = raw.get("external_enabled", False)
        if not isinstance(route_enabled, bool):
            raise ValidationError("artifacts.archive.external_enabled must be a boolean")
        return cls(
            route_id=route_id,
            root=root,
            roles=roles,
            machine_enabled=bool(machine_enabled),
            external_enabled=route_enabled,
            max_attempts=max_attempts,
        )


class StagedStorageAdapter:
    """Checksum-first staging and atomic publication for local or explicitly enabled NAS roots."""

    def __init__(self, root: Path, *, remote: bool = False, external_enabled: bool = False):
        self.root = root
        self.remote = remote
        self.external_enabled = external_enabled

    def _guard(self) -> None:
        text = str(self.root)
        is_unc = text.startswith("\\\\") or text.startswith("//")
        if (self.remote or is_unc) and not self.external_enabled:
            raise ExternalExecutionDisabled("Remote/NAS artifact publication is disabled by default")

    def publish_file(self, source: Path, logical_name: str | None = None) -> PublishedBlob:
        self._guard()
        if not source.is_file():
            raise ValidationError(f"Artifact source does not exist: {source}")
        name = logical_name or source.name
        if Path(name).name != name or name in {"", ".", ".."}:
            raise ValidationError("Artifact logical name must be a single filename")
        staging = self.root / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        temporary = staging / f"{uuid.uuid4()}.part"
        try:
            with source.open("rb") as reader, temporary.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
            checksum = sha256_file(temporary)
            size = temporary.stat().st_size
            destination = self.root / "sha256" / checksum[:2] / checksum / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if not destination.is_file() or sha256_file(destination) != checksum:
                    raise ArtifactCorruption(f"Existing content-addressed artifact is corrupt: {destination}")
                temporary.unlink()
            else:
                os.replace(temporary, destination)
                destination.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
            return PublishedBlob(destination, checksum, size)
        finally:
            if temporary.exists():
                temporary.unlink()

    def verify(self, blob: PublishedBlob) -> bool:
        if not blob.path.is_file() or blob.path.stat().st_size != blob.size_bytes:
            return False
        return sha256_file(blob.path) == blob.sha256


class LocalArtifactStorage(StagedStorageAdapter):
    def __init__(self, root: Path):
        super().__init__(root, remote=False, external_enabled=True)


class NasArtifactStorage(StagedStorageAdapter):
    def __init__(self, root: Path, *, external_enabled: bool = False):
        super().__init__(root, remote=True, external_enabled=external_enabled)


class ArtifactPublisher:
    def __init__(
        self,
        database: QueueDatabase,
        root: Path,
        *,
        archive_route: ArchiveRoute | None = None,
    ):
        self.database = database
        self.root = root
        self.storage = LocalArtifactStorage(root)
        self.archive_route = archive_route

    def publish(
        self,
        *,
        job_id: str,
        attempt_id: str | None,
        role: str,
        source: Path,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        blob = self.storage.publish_file(source)
        artifact_id = str(uuid.uuid4())
        record = {
            "artifact_id": artifact_id,
            "job_id": job_id,
            "attempt_id": attempt_id,
            "role": role,
            "path": str(blob.path),
            "sha256": blob.sha256,
            "size_bytes": blob.size_bytes,
            "published_at": utc_now(),
            "provenance": provenance,
        }
        record["record_sha256"] = sha256_bytes(canonical_json_bytes(record))
        record_path = self.root / "provenance" / job_id / f"{artifact_id}.json"
        atomic_write_json(record_path, record)
        record_path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        record["provenance_record"] = str(record_path)
        self.database.add_artifact(
            artifact_id=artifact_id,
            job_id=job_id,
            attempt_id=attempt_id,
            role=role,
            path=str(blob.path),
            sha256=blob.sha256,
            size_bytes=blob.size_bytes,
            provenance=record,
        )
        if self.archive_route and self.archive_route.includes(role):
            self.database.create_archive_operation(
                artifact_id=artifact_id,
                route_id=self.archive_route.route_id,
                route_fingerprint=self.archive_route.fingerprint,
                logical_name=blob.path.name,
            )
        return record

    def verify(self, job_id: str | None = None) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for row in self.database.list_artifacts(job_id):
            path = Path(row["path"])
            actual = sha256_file(path) if path.is_file() else None
            content_valid = (
                actual == row["sha256"] and path.is_file() and path.stat().st_size == row["size_bytes"]
            )
            provenance_valid = False
            try:
                database_record = json.loads(row["provenance_json"])
                record_path = Path(database_record["provenance_record"])
                file_record = json.loads(record_path.read_text(encoding="utf-8"))
                expected_record_hash = file_record.pop("record_sha256")
                provenance_valid = (
                    sha256_bytes(canonical_json_bytes(file_record)) == expected_record_hash
                    and file_record["artifact_id"] == row["artifact_id"]
                    and file_record["sha256"] == row["sha256"]
                    and file_record["path"] == row["path"]
                )
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                provenance_valid = False
            valid = content_valid and provenance_valid
            findings.append(
                {
                    "artifact_id": row["artifact_id"],
                    "job_id": row["job_id"],
                    "valid": valid,
                    "expected_sha256": row["sha256"],
                    "actual_sha256": actual,
                    "content_valid": content_valid,
                    "provenance_valid": provenance_valid,
                }
            )
        return findings


class ArchiveDrainer:
    """Processes only archive operations; it never changes or retries an analysis job."""

    def __init__(self, database: QueueDatabase, route: ArchiveRoute):
        self.database = database
        self.route = route
        self.storage = NasArtifactStorage(route.root, external_enabled=route.enabled)

    def drain(self, limit: int = 100) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for operation in self.database.claim_archive_operations(self.route.route_id, limit=limit):
            state = "FAILED"
            reason = "ARCHIVE_INTERNAL_ERROR"
            receipt: PublishedBlob | None = None
            try:
                if operation["route_fingerprint"] != self.route.fingerprint:
                    raise ExternalExecutionDisabled("Archive route fingerprint does not match the queued approval")
                if not self.route.enabled:
                    raise ExternalExecutionDisabled("Both archive enable switches must be true")
                source = Path(operation["source_path"])
                if not source.is_file():
                    raise ArtifactCorruption("Local immutable artifact is missing")
                if source.stat().st_size != int(operation["expected_size_bytes"]):
                    raise ArtifactCorruption("Local immutable artifact size changed")
                if sha256_file(source) != operation["expected_sha256"]:
                    raise ArtifactCorruption("Local immutable artifact checksum changed")
                receipt = self.storage.publish_file(source, operation["logical_name"])
                if (
                    receipt.sha256 != operation["expected_sha256"]
                    or receipt.size_bytes != int(operation["expected_size_bytes"])
                    or not self.storage.verify(receipt)
                ):
                    raise ArtifactCorruption("Archive verification did not match the local artifact")
                state = "SUCCEEDED"
                reason = "ARCHIVE_VERIFIED"
            except ExternalExecutionDisabled:
                state = "BLOCKED"
                reason = "ARCHIVE_EXTERNAL_DISABLED"
            except (ArtifactCorruption, ValidationError) as exc:
                state = "FAILED"
                reason = exc.code
            except OSError:
                state = "RETRY" if int(operation["attempt_no"]) < self.route.max_attempts else "FAILED"
                reason = "ARCHIVE_IO_RETRY" if state == "RETRY" else "ARCHIVE_IO_ATTEMPTS_EXHAUSTED"
            except Exception:
                # Keep integration defects separate from the already committed analysis result.
                state = "FAILED"
                reason = "ARCHIVE_INTERNAL_ERROR"
            self.database.record_archive_result(
                operation["operation_id"],
                state,
                reason,
                archive_path=str(receipt.path) if receipt else None,
                archive_sha256=receipt.sha256 if receipt else None,
                archive_size_bytes=receipt.size_bytes if receipt else None,
                details={"attempt_no": int(operation["attempt_no"])},
            )
            results.append(
                {
                    "operation_id": operation["operation_id"],
                    "job_id": operation["job_id"],
                    "artifact_id": operation["artifact_id"],
                    "attempt_no": int(operation["attempt_no"]),
                    "state": state,
                    "reason_code": reason,
                }
            )
        return results


def archive_rollup(operations: list[dict[str, Any]]) -> str:
    if not operations:
        return "NOT_REQUESTED"
    states = {str(operation.get("state")) for operation in operations}
    if states == {"SUCCEEDED"}:
        return "COMPLETE"
    if "FAILED" in states:
        return "FAILED"
    if "BLOCKED" in states:
        return "BLOCKED"
    if "EXECUTING" in states:
        return "EXECUTING"
    return "PENDING"
