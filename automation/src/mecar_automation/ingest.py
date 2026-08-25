from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .db import SubmitResult
from .errors import AutomationError
from .util import atomic_write_json, load_json, utc_now
from .validation import manifest_hash, validate_manifest


@dataclass(frozen=True)
class IntakeResult:
    source: str
    disposition: str
    job_id: str | None
    code: str


class HotFolder:
    """Consumes manifest.json only after a sibling manifest.json.ready commit marker exists."""

    def __init__(
        self,
        root: Path,
        submit: Callable[[dict], SubmitResult],
        *,
        stable_seconds: float = 1.0,
        probe_seconds: float = 0.02,
    ):
        self.root = root
        self.incoming = root / "incoming"
        self.accepted = root / "accepted"
        self.quarantine = root / "quarantine"
        self.receipts = root / "receipts"
        self.submit = submit
        self.stable_seconds = stable_seconds
        self.probe_seconds = probe_seconds
        for directory in (self.incoming, self.accepted, self.quarantine, self.receipts):
            directory.mkdir(parents=True, exist_ok=True)

    def scan(self) -> list[IntakeResult]:
        results: list[IntakeResult] = []
        for marker in sorted(self.incoming.glob("*.json.ready")):
            manifest_path = Path(str(marker)[: -len(".ready")])
            if not manifest_path.is_file():
                results.append(self._quarantine(marker, None, "READY_WITHOUT_MANIFEST", "Ready marker has no manifest"))
                continue
            if not self._stable(manifest_path, marker):
                results.append(IntakeResult(str(manifest_path), "DEFERRED", None, "FILE_NOT_STABLE"))
                continue
            try:
                manifest = validate_manifest(load_json(manifest_path))
                checksum = manifest_hash(manifest)
                submit_result = self.submit(manifest)
                destination = self.accepted / manifest["submission_id"] / checksum
                destination.mkdir(parents=True, exist_ok=True)
                self._move_once(manifest_path, destination / manifest_path.name)
                self._move_once(marker, destination / marker.name)
                result = IntakeResult(
                    str(manifest_path), submit_result.disposition, submit_result.job_id, submit_result.disposition
                )
                self._receipt(result, checksum)
            except AutomationError as exc:
                result = self._quarantine(marker, manifest_path, exc.code, str(exc))
            except Exception as exc:
                result = self._quarantine(marker, manifest_path, "INTAKE_INTERNAL_ERROR", type(exc).__name__)
            results.append(result)
        return results

    def _stable(self, manifest: Path, marker: Path) -> bool:
        before = (manifest.stat().st_size, manifest.stat().st_mtime_ns, marker.stat().st_mtime_ns)
        age = time.time() - max(manifest.stat().st_mtime, marker.stat().st_mtime)
        if self.stable_seconds > 0 and age < self.stable_seconds:
            return False
        if self.probe_seconds:
            time.sleep(self.probe_seconds)
        if not manifest.exists() or not marker.exists():
            return False
        after = (manifest.stat().st_size, manifest.stat().st_mtime_ns, marker.stat().st_mtime_ns)
        return before == after and before[0] > 0

    @staticmethod
    def _move_once(source: Path, destination: Path) -> None:
        if destination.exists():
            source.unlink()
        else:
            os.replace(source, destination)

    def _quarantine(
        self, marker: Path, manifest: Path | None, code: str, detail: str
    ) -> IntakeResult:
        token = f"{utc_now().replace(':', '').replace('.', '')}-{uuid.uuid4().hex[:8]}"
        target = self.quarantine / token
        target.mkdir(parents=True, exist_ok=False)
        if manifest and manifest.exists():
            os.replace(manifest, target / manifest.name)
        if marker.exists():
            os.replace(marker, target / marker.name)
        receipt = {
            "disposition": "QUARANTINED",
            "code": code,
            "detail": detail[:500],
            "source_name": manifest.name if manifest else marker.name,
            "recorded_at": utc_now(),
        }
        atomic_write_json(target / "receipt.json", receipt)
        return IntakeResult(receipt["source_name"], "QUARANTINED", None, code)

    def _receipt(self, result: IntakeResult, checksum: str) -> None:
        path = self.receipts / f"{result.job_id}-{uuid.uuid4().hex[:8]}.json"
        atomic_write_json(
            path,
            {
                "job_id": result.job_id,
                "disposition": result.disposition,
                "manifest_sha256": checksum,
                "recorded_at": utc_now(),
            },
        )
