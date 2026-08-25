from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROFILES = PACKAGE_ROOT / "config" / "profiles"
EXAMPLES = PACKAGE_ROOT / "examples"


def manifest(
    submission_id: str,
    *,
    mode: str = "success",
    timeout: float = 2.0,
    recipients: list[str] | None = None,
) -> dict:
    return {
        "schema_version": "1.0.0",
        "submission_id": submission_id,
        "profile": {"id": "dummy-standard", "version": "1.0.0"},
        "adapter": "dummy",
        "timeout_sec": timeout,
        "parameters": {"mode": mode, "delay_sec": 0},
        "resources": {"cpu": 1, "memory_mb": 64, "licenses": {}},
        "notification": {"recipients": recipients or []},
    }

