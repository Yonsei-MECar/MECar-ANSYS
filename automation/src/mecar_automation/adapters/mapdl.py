from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..errors import ValidationError
from .base import AdapterOutcome, AnalysisAdapter, PreparedRun
from .external import mandatory_artifacts, stage_approved_input


class MapdlV211Adapter(AnalysisAdapter):
    name = "mapdl_v211"

    def prepare(
        self,
        manifest: dict[str, Any],
        profile: dict[str, Any],
        workdir: Path,
        *,
        external_execution_enabled: bool,
    ) -> PreparedRun:
        del manifest
        if profile["adapter"] != self.name or not profile["enabled"]:
            raise ValidationError("MAPDL v211 profile is disabled or has the wrong adapter")
        executable, staged = stage_approved_input(
            profile, workdir, "approved_input.dat", external_execution_enabled=external_execution_enabled
        )
        if executable.name.casefold() not in {"ansys211.exe", "mapdl.exe"}:
            raise ValidationError("MAPDL executable filename is not approved by the v211 port")
        if staged.suffix.casefold() != ".dat":
            raise ValidationError("MAPDL approved input must be a DAT file")
        output = workdir / "solver.out"
        command = (
            str(executable),
            "-b",
            "-np",
            str(profile["resources"]["cpu"]),
            "-i",
            str(staged),
            "-o",
            str(output),
            "-dir",
            str(workdir),
        )
        return PreparedRun(command)

    def evaluate(self, workdir: Path, process: Any) -> AdapterOutcome:
        artifacts: list[tuple[str, Path]] = []
        for role, name in (
            ("solver_stdout", "stdout.log"),
            ("solver_stderr", "stderr.log"),
            ("mapdl_output", "solver.out"),
        ):
            path = workdir / name
            if path.is_file():
                artifacts.append((role, path))
        if process.timed_out:
            return AdapterOutcome(False, "MAPDL_TIMEOUT", {}, tuple(artifacts))
        if process.cancelled:
            return AdapterOutcome(False, "MAPDL_CANCELLED", {}, tuple(artifacts))
        output = workdir / "solver.out"
        if process.exit_code != 0 or not output.is_file() or output.stat().st_size == 0:
            return AdapterOutcome(False, "MAPDL_EXECUTION_FAILED", {}, tuple(artifacts))
        text = output.read_text(encoding="utf-8", errors="replace").upper()
        fatal_markers = ("*** ERROR ***", "LICENSE MANAGER ERROR", "FATAL ERROR")
        if any(marker in text for marker in fatal_markers):
            return AdapterOutcome(False, "MAPDL_FATAL_EVIDENCE", {}, tuple(artifacts))
        required = mandatory_artifacts(workdir, getattr(process, "adapter_settings", {}))
        if required is None:
            return AdapterOutcome(False, "MAPDL_MANDATORY_OUTPUT_MISSING", {}, tuple(artifacts))
        artifacts.extend(required)
        metrics_path = workdir / "metrics.json"
        try:
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AdapterOutcome(False, "MAPDL_EVIDENCE_INVALID", {}, tuple(artifacts))
        checks = metrics.get("checks")
        if (
            metrics.get("schema_version") != "1.0.0"
            or metrics.get("solver_release") != "211"
            or metrics.get("engineering_outcome") != "PASSED"
            or not isinstance(checks, list)
            or not checks
            or not all(isinstance(item, dict) and item.get("passed") is True for item in checks)
        ):
            return AdapterOutcome(False, "MAPDL_ENGINEERING_CHECK_FAILED", {}, tuple(artifacts))
        numeric_metrics = metrics.get("metrics", {})
        if not isinstance(numeric_metrics, dict) or not numeric_metrics or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
            for value in numeric_metrics.values()
        ):
            return AdapterOutcome(False, "MAPDL_METRICS_INVALID", {}, tuple(artifacts))
        return AdapterOutcome(True, "MAPDL_SOLVED", numeric_metrics, tuple(artifacts))
