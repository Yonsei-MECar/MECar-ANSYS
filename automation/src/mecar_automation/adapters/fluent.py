from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..errors import ValidationError
from .base import AdapterOutcome, AnalysisAdapter, PreparedRun
from .external import mandatory_artifacts, stage_approved_input


class FluentV211Adapter(AnalysisAdapter):
    name = "fluent_v211"

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
            raise ValidationError("Fluent v211 profile is disabled or has the wrong adapter")
        executable, staged = stage_approved_input(
            profile, workdir, "approved_input.jou", external_execution_enabled=external_execution_enabled
        )
        if executable.name.casefold() != "fluent.exe":
            raise ValidationError("Fluent executable filename is not approved by the v211 port")
        if staged.suffix.casefold() != ".jou":
            raise ValidationError("Fluent approved input must be a JOU file")
        mode = profile["settings"]["dimension_precision"]
        return PreparedRun(
            (str(executable), mode, f"-t{profile['resources']['cpu']}", "-g", "-i", str(staged))
        )

    def evaluate(self, workdir: Path, process: Any) -> AdapterOutcome:
        artifacts: list[tuple[str, Path]] = []
        for role, name in (("solver_stdout", "stdout.log"), ("solver_stderr", "stderr.log")):
            path = workdir / name
            if path.is_file():
                artifacts.append((role, path))
        if process.timed_out:
            return AdapterOutcome(False, "FLUENT_TIMEOUT", {}, tuple(artifacts))
        if process.cancelled:
            return AdapterOutcome(False, "FLUENT_CANCELLED", {}, tuple(artifacts))
        if process.exit_code != 0:
            return AdapterOutcome(False, "FLUENT_EXECUTION_FAILED", {}, tuple(artifacts))
        transcript = ""
        for name in ("stdout.log", "stderr.log"):
            path = workdir / name
            if path.is_file():
                transcript += path.read_text(encoding="utf-8", errors="replace").upper()
        if any(marker in transcript for marker in ("LICENSE ERROR", "ERROR:", "SEGMENTATION VIOLATION")):
            return AdapterOutcome(False, "FLUENT_FATAL_EVIDENCE", {}, tuple(artifacts))
        required = mandatory_artifacts(workdir, getattr(process, "adapter_settings", {}))
        if required is None:
            return AdapterOutcome(False, "FLUENT_MANDATORY_OUTPUT_MISSING", {}, tuple(artifacts))
        artifacts.extend(required)
        try:
            metrics = json.loads((workdir / "metrics.json").read_text(encoding="utf-8"))
            convergence = json.loads((workdir / "convergence.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AdapterOutcome(False, "FLUENT_EVIDENCE_INVALID", {}, tuple(artifacts))
        required_metrics = ("drag_n", "downforce_n", "cd", "cl")
        values = metrics.get("metrics", {})
        valid_values = isinstance(values, dict) and all(
            isinstance(values.get(name), (int, float))
            and not isinstance(values.get(name), bool)
            and math.isfinite(float(values[name]))
            for name in required_metrics
        )
        residuals = convergence.get("residuals", {})
        valid_residuals = isinstance(residuals, dict) and bool(residuals) and all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
            for value in residuals.values()
        )
        if (
            metrics.get("schema_version") != "1.0.0"
            or metrics.get("solver_release") != "211"
            or metrics.get("engineering_outcome") != "PASSED"
            or not valid_values
            or convergence.get("schema_version") != "1.0.0"
            or convergence.get("converged") is not True
            or convergence.get("force_monitor_stable") is not True
            or not isinstance(convergence.get("mass_imbalance_percent"), (int, float))
            or isinstance(convergence.get("mass_imbalance_percent"), bool)
            or not math.isfinite(float(convergence["mass_imbalance_percent"]))
            or not valid_residuals
        ):
            return AdapterOutcome(False, "FLUENT_ENGINEERING_CHECK_FAILED", {}, tuple(artifacts))
        return AdapterOutcome(True, "FLUENT_SOLVED", {name: float(values[name]) for name in required_metrics}, tuple(artifacts))
