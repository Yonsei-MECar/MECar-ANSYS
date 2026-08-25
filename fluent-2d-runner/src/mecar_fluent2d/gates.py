from __future__ import annotations

import math
from typing import Any


RESIDUAL_KEYS = ("continuity", "x-velocity", "y-velocity", "k", "omega")


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _relative_range(values: list[Any]) -> float | None:
    if not values or not all(_finite(value) for value in values):
        return None
    absolute = [abs(float(value)) for value in values]
    mean = sum(absolute) / len(absolute)
    return (max(absolute) - min(absolute)) / max(mean, 1e-12)


def evaluate_engineering_gates(
    manifest: dict[str, Any],
    parsed: dict[str, Any],
    *,
    present_artifacts: set[str],
    mesh_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    configuration = manifest["convergence"]
    residual_limits = configuration["residualMax"]
    latest_residual = parsed.get("latestResidual") or {}
    residual_checks = {
        key: {
            "value": latest_residual.get(key),
            "limit": residual_limits[key],
            "passed": _finite(latest_residual.get(key)) and float(latest_residual[key]) <= float(residual_limits[key]),
        }
        for key in RESIDUAL_KEYS
    }
    mass_ratio = parsed.get("massImbalanceRatio")
    mass_check = {
        "value": mass_ratio,
        "limit": configuration["massImbalanceRatioMax"],
        "passed": _finite(mass_ratio) and abs(float(mass_ratio)) <= float(configuration["massImbalanceRatioMax"]),
    }
    samples = parsed.get("forceSamples") or []
    minimum = int(configuration["forcePlateauMinSamples"])
    window = samples[-minimum:] if len(samples) >= minimum else []
    drag_relative_range = _relative_range([sample.get("dragN") for sample in window])
    lift_relative_range = _relative_range([sample.get("liftN") for sample in window])
    component_ranges = [value for value in (drag_relative_range, lift_relative_range) if value is not None]
    relative_range = max(component_ranges) if len(component_ranges) == 2 else None
    plateau_check = {
        "sampleCount": len(samples),
        "requiredSamples": minimum,
        "relativeRange": relative_range,
        "dragRelativeRange": drag_relative_range,
        "liftRelativeRange": lift_relative_range,
        "limit": configuration["forcePlateauRelativeRangeMax"],
        "passed": _finite(relative_range) and float(relative_range) <= float(configuration["forcePlateauRelativeRangeMax"]),
    }
    raw_force = parsed.get("rawForce") or {}
    coefficient = parsed.get("coefficient") or {}
    force_check = {
        "rawFxN": raw_force.get("fxN"),
        "rawFyN": raw_force.get("fyN"),
        "Cd": coefficient.get("Cd"),
        "C_DF": coefficient.get("C_DF"),
        "passed": all(_finite(value) for value in (raw_force.get("fxN"), raw_force.get("fyN"), coefficient.get("Cd"), coefficient.get("C_DF"))),
    }
    required = set(manifest["artifacts"]["required"])
    missing = sorted(required - present_artifacts)
    artifact_check = {"required": sorted(required), "missing": missing, "passed": not missing}
    mesh = mesh_quality or {}
    mesh_check = {
        "passed": mesh.get("passed") is True,
        "gmshVersion": mesh.get("gmshVersion"),
        "generatorVersion": mesh.get("generatorVersion"),
        "minimumCellAreaM2": mesh.get("minimumCellAreaM2"),
        "minimumNormalizedCellQuality": mesh.get("minimumNormalizedTriangleQuality"),
    }
    checks = {
        "meshQuality": mesh_check,
        "residuals": residual_checks,
        "massBalance": mass_check,
        "forcePlateau": plateau_check,
        "finiteForcesAndCoefficients": force_check,
        "artifacts": artifact_check,
    }
    passed = (
        mesh_check["passed"]
        and all(value["passed"] for value in residual_checks.values())
        and mass_check["passed"]
        and plateau_check["passed"]
        and force_check["passed"]
        and artifact_check["passed"]
    )
    return {"passed": passed, "checks": checks}
