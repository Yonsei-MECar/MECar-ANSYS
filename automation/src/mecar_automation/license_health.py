from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import ValidationError
from .util import require_safe_component, sha256_file


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SERVER = re.compile(r"^(?P<port>[0-9]{1,5})@(?P<host>[A-Za-z0-9](?:[A-Za-z0-9.-]{0,252}[A-Za-z0-9])?)$")
_FEATURE = re.compile(
    r"Users of\s+([A-Za-z0-9_.-]+):\s*\(Total of\s+([0-9]+)\s+licenses?\s+issued;\s*"
    r"Total of\s+([0-9]+)\s+licenses?\s+in use\)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LicenseProbeSettings:
    adapter: str = "disabled"
    machine_enabled: bool = False
    external_enabled: bool = False
    executable: Path | None = None
    executable_sha256: str | None = None
    server: str | None = None
    features: tuple[str, ...] = ()
    timeout_sec: float = 5.0

    @property
    def enabled(self) -> bool:
        return self.adapter == "lmutil" and self.machine_enabled and self.external_enabled

    @classmethod
    def from_config(
        cls,
        raw: dict[str, Any] | None,
        *,
        machine_enabled: bool,
    ) -> LicenseProbeSettings:
        if raw is None:
            return cls(machine_enabled=machine_enabled)
        if not isinstance(raw, dict):
            raise ValidationError("license_probe must be an object")
        adapter = raw.get("adapter", "disabled")
        if adapter == "disabled":
            return cls(machine_enabled=machine_enabled)
        if adapter != "lmutil":
            raise ValidationError("license_probe.adapter must be disabled or lmutil")
        external_enabled = raw.get("external_enabled", False)
        if not isinstance(external_enabled, bool):
            raise ValidationError("license_probe.external_enabled must be boolean")
        executable_value = raw.get("executable")
        if not isinstance(executable_value, str) or not executable_value or "\x00" in executable_value:
            raise ValidationError("license_probe.executable must be an absolute lmutil/lmstat path")
        executable = Path(executable_value)
        if not executable.is_absolute() or executable.name.casefold() not in {
            "lmutil.exe",
            "lmstat.exe",
            "lmutil",
            "lmstat",
        }:
            raise ValidationError("license_probe.executable must be an absolute lmutil/lmstat path")
        executable_sha256 = raw.get("executable_sha256")
        if not isinstance(executable_sha256, str) or not _SHA256.fullmatch(executable_sha256):
            raise ValidationError("license_probe.executable_sha256 must be lowercase SHA-256")
        server = raw.get("server")
        match = _SERVER.fullmatch(server) if isinstance(server, str) else None
        if match is None or not 1 <= int(match.group("port")) <= 65535:
            raise ValidationError("license_probe.server must be an explicit port@host value")
        raw_features = raw.get("features")
        if not isinstance(raw_features, list) or not raw_features or len(raw_features) > 32:
            raise ValidationError("license_probe.features must contain 1 to 32 feature names")
        features = tuple(require_safe_component(value, "license_probe.features[]") for value in raw_features)
        if len({value.casefold() for value in features}) != len(features):
            raise ValidationError("license_probe.features contains duplicates")
        timeout = raw.get("timeout_sec", 5.0)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.1 <= float(timeout) <= 30.0:
            raise ValidationError("license_probe.timeout_sec must be from 0.1 to 30 seconds")
        return cls(
            adapter="lmutil",
            machine_enabled=machine_enabled,
            external_enabled=external_enabled,
            executable=executable,
            executable_sha256=executable_sha256,
            server=server,
            features=features,
            timeout_sec=float(timeout),
        )


def _parse_lmstat(output: str, requested: tuple[str, ...]) -> dict[str, dict[str, int]] | None:
    if not re.search(r"license server\s+UP", output, re.IGNORECASE):
        return None
    parsed = {
        match.group(1).casefold(): {
            "issued": int(match.group(2)),
            "in_use": int(match.group(3)),
            "available": max(0, int(match.group(2)) - int(match.group(3))),
        }
        for match in _FEATURE.finditer(output)
    }
    if any(feature.casefold() not in parsed for feature in requested):
        return None
    return {feature: parsed[feature.casefold()] for feature in requested}


def probe_license_status(
    settings: LicenseProbeSettings,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    base = {
        "adapter": settings.adapter,
        "configured": settings.adapter == "lmutil",
        "machine_enabled": settings.machine_enabled,
        "route_enabled": settings.external_enabled,
        "live_access_attempted": False,
    }
    if settings.adapter == "disabled":
        return {**base, "status": "DISABLED", "reason_code": "LICENSE_PROBE_NOT_CONFIGURED"}
    if not settings.enabled:
        return {**base, "status": "BLOCKED", "reason_code": "LICENSE_PROBE_TWO_GATES_REQUIRED"}
    assert settings.executable is not None
    assert settings.executable_sha256 is not None
    assert settings.server is not None
    if not settings.executable.is_file():
        return {**base, "status": "ERROR", "reason_code": "LICENSE_PROBE_EXECUTABLE_MISSING"}
    try:
        if sha256_file(settings.executable) != settings.executable_sha256:
            return {**base, "status": "ERROR", "reason_code": "LICENSE_PROBE_EXECUTABLE_HASH_MISMATCH"}
    except OSError:
        return {**base, "status": "ERROR", "reason_code": "LICENSE_PROBE_EXECUTABLE_UNREADABLE"}
    command = [str(settings.executable)]
    if settings.executable.name.casefold() in {"lmutil.exe", "lmutil"}:
        command.append("lmstat")
    command.extend(["-a", "-c", settings.server])
    environment = os.environ.copy()
    environment.pop("LM_LICENSE_FILE", None)
    environment.pop("ANSYSLMD_LICENSE_FILE", None)
    started = time.monotonic()
    try:
        completed = runner(
            command,
            cwd=settings.executable.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.timeout_sec,
            check=False,
            shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except subprocess.TimeoutExpired:
        return {
            **base,
            "live_access_attempted": True,
            "status": "ERROR",
            "reason_code": "LICENSE_PROBE_TIMEOUT",
        }
    except OSError:
        return {
            **base,
            "live_access_attempted": True,
            "status": "ERROR",
            "reason_code": "LICENSE_PROBE_EXECUTION_FAILED",
        }
    elapsed = round(time.monotonic() - started, 6)
    if completed.returncode != 0:
        return {
            **base,
            "live_access_attempted": True,
            "status": "ERROR",
            "reason_code": "LICENSE_PROBE_NONZERO_EXIT",
            "exit_code": completed.returncode,
            "duration_sec": elapsed,
        }
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if len(output.encode("utf-8", errors="replace")) > 1024 * 1024:
        return {
            **base,
            "live_access_attempted": True,
            "status": "ERROR",
            "reason_code": "LICENSE_PROBE_OUTPUT_TOO_LARGE",
            "duration_sec": elapsed,
        }
    features = _parse_lmstat(output, settings.features)
    if features is None:
        return {
            **base,
            "live_access_attempted": True,
            "status": "ERROR",
            "reason_code": "LICENSE_PROBE_PARSE_FAILED",
            "duration_sec": elapsed,
        }
    exhausted = any(item["available"] < 1 for item in features.values())
    return {
        **base,
        "live_access_attempted": True,
        "status": "EXHAUSTED" if exhausted else "AVAILABLE",
        "reason_code": "LICENSE_FEATURE_EXHAUSTED" if exhausted else "LICENSE_PROBE_OK",
        "duration_sec": elapsed,
        "features": features,
    }
