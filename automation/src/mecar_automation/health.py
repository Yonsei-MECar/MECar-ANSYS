from __future__ import annotations

import ctypes
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .engine import AutomationEngine
from .license_health import LicenseProbeSettings, probe_license_status
from .supervisor import process_is_alive
from .util import load_json, utc_now
from .validation import validate_profile


def _memory_status() -> dict[str, int | None]:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        value = MemoryStatus()
        value.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            return {
                "total_mb": int(value.total_physical // (1024 * 1024)),
                "available_mb": int(value.available_physical // (1024 * 1024)),
                "load_percent": int(value.memory_load),
            }
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        total = page_size * int(os.sysconf("SC_PHYS_PAGES"))
        available = page_size * int(os.sysconf("SC_AVPHYS_PAGES"))
        return {
            "total_mb": total // (1024 * 1024),
            "available_mb": available // (1024 * 1024),
            "load_percent": round(100 * (total - available) / total) if total else None,
        }
    except (AttributeError, OSError, ValueError):
        return {"total_mb": None, "available_mb": None, "load_percent": None}


def _agent_status(runtime_root: Path) -> dict[str, Any]:
    path = runtime_root / "state" / "agent.status.json"
    if not path.is_file():
        return {"state": "STOPPED", "status_file": str(path), "pid_alive": False}
    try:
        if path.stat().st_size > 64 * 1024:
            raise ValueError("status file too large")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("status must be an object")
        pid = value.get("pid")
        state = str(value.get("state", "UNKNOWN"))
        alive = state in {"STARTING", "RUNNING", "STOPPING"} and isinstance(pid, int) and process_is_alive(pid)
        result = {
            "state": state,
            "pid": pid if isinstance(pid, int) else None,
            "pid_alive": alive,
            "started_at": value.get("started_at"),
            "last_cycle_at": value.get("last_cycle_at"),
            "cycle_count": value.get("cycle_count", 0),
            "last_error_code": value.get("last_error_code"),
            "status_file": str(path),
        }
        if result["state"] in {"RUNNING", "STOPPING"} and not alive:
            result["state"] = "STALE"
        return result
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return {"state": "CORRUPT", "status_file": str(path), "pid_alive": False}


def _profile_inventory(engine: AutomationEngine) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for path in sorted(engine.profiles.root.glob("*.json")):
        try:
            profile = validate_profile(load_json(path))
            profiles.append(
                {
                    "profile_id": profile["profile_id"],
                    "version": profile["version"],
                    "adapter": profile["adapter"],
                    "enabled": profile["enabled"],
                    "external_profile_enabled": profile.get("external_execution_enabled", False),
                    "valid": True,
                }
            )
        except Exception:
            profiles.append({"profile_file": path.name, "valid": False})
    return profiles


def build_health_report(
    engine: AutomationEngine,
    config: dict[str, Any],
    license_settings: LicenseProbeSettings,
) -> dict[str, Any]:
    database = engine.database.health()
    operations = engine.database.operational_snapshot()
    disk = shutil.disk_usage(engine.runtime_root)
    disk_free_mb = int(disk.free // (1024 * 1024))
    disk_report = {
        "total_mb": int(disk.total // (1024 * 1024)),
        "used_mb": int(disk.used // (1024 * 1024)),
        "free_mb": disk_free_mb,
        "minimum_free_mb": engine.supervisor.minimum_free_disk_mb,
        "reserve_ok": disk_free_mb >= engine.supervisor.minimum_free_disk_mb,
    }
    hotfolder = engine.runtime_root / "hotfolder"
    incoming = hotfolder / "incoming"
    notification = config.get("notification", {"adapter": "fake"})
    notification_adapter = notification.get("adapter", "fake") if isinstance(notification, dict) else "invalid"
    raw_machine_notification_enabled = config.get("external_notification_enabled", False)
    raw_route_notification_enabled = (
        notification.get("external_send_enabled", False) if isinstance(notification, dict) else False
    )
    notification_config_valid = (
        notification_adapter in {"fake", "smtp"}
        and isinstance(raw_machine_notification_enabled, bool)
        and isinstance(raw_route_notification_enabled, bool)
    )
    machine_notification_enabled = (
        raw_machine_notification_enabled if isinstance(raw_machine_notification_enabled, bool) else False
    )
    route_notification_enabled = (
        raw_route_notification_enabled if isinstance(raw_route_notification_enabled, bool) else False
    )
    if notification_adapter == "fake":
        notification_status = "FAKE_LOCAL"
    elif machine_notification_enabled and route_notification_enabled:
        notification_status = "ENABLED"
    else:
        notification_status = "DISABLED"
    route = engine.archive_route
    license_report = probe_license_status(license_settings)
    profiles = _profile_inventory(engine)
    degraded_reasons: list[str] = []
    if database["integrity"] != "ok":
        degraded_reasons.append("DATABASE_INTEGRITY")
    if not disk_report["reserve_ok"]:
        degraded_reasons.append("DISK_RESERVE")
    if license_settings.enabled and license_report["status"] not in {"AVAILABLE"}:
        degraded_reasons.append(license_report["reason_code"])
    if any(not profile.get("valid", False) for profile in profiles):
        degraded_reasons.append("PROFILE_INVALID")
    if not notification_config_valid:
        degraded_reasons.append("NOTIFICATION_CONFIG_INVALID")
    return {
        "schema_version": "1.0.0",
        "status": "DEGRADED" if degraded_reasons else "OK",
        "checked_at": utc_now(),
        "degraded_reasons": degraded_reasons,
        "database": database,
        "system": {
            "cpu": {
                "logical_count": os.cpu_count(),
                "scheduler": engine.supervisor.gate.snapshot(),
            },
            "ram": _memory_status(),
            "disk": disk_report,
        },
        "queue": {
            "job_states": operations["jobs"],
            "incoming_ready": len(list(incoming.glob("*.ready"))) if incoming.is_dir() else 0,
            "paused": database["paused"],
        },
        "recent_errors": operations["recent_errors"],
        "agent": _agent_status(engine.runtime_root),
        "providers": {
            "solver": {
                "machine_external_execution_enabled": engine.external_execution_enabled,
                "profiles": profiles,
            },
            "archive": {
                "configured": route is not None,
                "enabled": route.enabled if route else False,
                "route_id": route.route_id if route else None,
                "states": operations["archive"],
                "pending": database["pending_archive"],
            },
            "notification": {
                "adapter": notification_adapter,
                "status": notification_status,
                "config_valid": notification_config_valid,
                "machine_enabled": machine_notification_enabled,
                "route_enabled": route_notification_enabled,
                "states": operations["notifications"],
                "pending": database["pending_outbox"],
            },
            "license": license_report,
        },
    }
