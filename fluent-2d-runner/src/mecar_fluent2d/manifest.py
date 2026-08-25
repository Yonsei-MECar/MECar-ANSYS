from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .errors import InputError, ManifestError
from .util import CASE_ID_RE, canonical_hash, resolve_under, safe_relative_path, sha256_file


SCHEMA_VERSION = "mecar.fluent2d.case/v1"
PROCEDURAL_NACA_RE = re.compile(r"^NACA([0-9]{4})$")


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{field} must be an object")
    return value


def _positive(value: Any, field: str, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (result < 0 if allow_zero else result <= 0):
        relation = "non-negative" if allow_zero else "positive"
        raise ManifestError(f"{field} must be finite and {relation}")
    return result


def load_manifest(path: str | Path) -> tuple[dict[str, Any], Path]:
    manifest_path = Path(path).resolve()
    try:
        with manifest_path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError as exc:
        raise InputError(f"manifest does not exist: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest JSON is invalid at line {exc.lineno}: {exc.msg}") from exc
    validate_manifest(data, manifest_path.parent)
    return data, manifest_path


def validate_manifest(data: Any, manifest_root: Path) -> None:
    root = _mapping(data, "manifest")
    if root.get("schemaVersion") != SCHEMA_VERSION:
        raise ManifestError(f"schemaVersion must equal {SCHEMA_VERSION!r}")
    case_id = root.get("caseId")
    if not isinstance(case_id, str) or not CASE_ID_RE.fullmatch(case_id):
        raise ManifestError("caseId must contain only letters, digits, dot, underscore, and hyphen")

    solver = _mapping(root.get("solver"), "solver")
    if solver.get("product") != "ANSYS Fluent":
        raise ManifestError("solver.product must be 'ANSYS Fluent'")
    if solver.get("release") != "2021 R1" or solver.get("tuiVersion") != "21.1":
        raise ManifestError("only Fluent 2021 R1 / TUI 21.1 is accepted")
    if solver.get("dimension") != "2d" or solver.get("precision") not in {"double", "single"}:
        raise ManifestError("solver must declare dimension=2d and precision=single|double")
    threads = solver.get("threads")
    if isinstance(threads, bool) or not isinstance(threads, int) or not 1 <= threads <= 8:
        raise ManifestError("solver.threads must be an integer from 1 through 8")

    mesh = _mapping(root.get("mesh"), "mesh")
    if mesh.get("backend") != "gmsh-4.13.1":
        raise ManifestError("mesh.backend must be pinned to gmsh-4.13.1")
    if mesh.get("generatorVersion") != "mecar-gmsh2d/v1":
        raise ManifestError("mesh.generatorVersion must be mecar-gmsh2d/v1")
    airfoil = _mapping(mesh.get("airfoil"), "mesh.airfoil")
    source_type = airfoil.get("sourceType")
    airfoil_id = airfoil.get("id")
    if not isinstance(airfoil_id, str) or not airfoil_id:
        raise ManifestError("mesh.airfoil.id is required")
    for field in ("source", "license"):
        if not isinstance(airfoil.get(field), str) or not airfoil[field].strip():
            raise ManifestError(f"mesh.airfoil.{field} is required")
        if airfoil[field].strip().upper().startswith("PENDING"):
            raise ManifestError(f"mesh.airfoil.{field} is still pending and cannot be used")
    if source_type == "procedural-naca4":
        match = PROCEDURAL_NACA_RE.fullmatch(airfoil_id.upper())
        if not match:
            raise ManifestError("procedural-naca4 requires an id such as NACA0012")
        if airfoil.get("generatorVersion") != "mecar-naca4/v1":
            raise ManifestError("procedural NACA input must pin generatorVersion=mecar-naca4/v1")
    elif source_type == "selig-dat":
        rel = safe_relative_path(airfoil.get("path"), field="mesh.airfoil.path")
        source_path = resolve_under(manifest_root, rel, field="mesh.airfoil.path")
        if not source_path.is_file():
            raise InputError(
                f"airfoil DAT is missing: {rel.as_posix()}",
                hint="Provide the licensed source file and its SHA-256; the runner will not substitute another profile.",
            )
        expected = airfoil.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
            raise ManifestError("mesh.airfoil.sha256 must be a 64-character checksum")
        actual = sha256_file(source_path)
        if actual.lower() != expected.lower():
            raise InputError(f"airfoil DAT checksum mismatch for {rel.as_posix()}")
    else:
        raise ManifestError("mesh.airfoil.sourceType must be procedural-naca4 or selig-dat")

    for field in ("chordM", "heightM", "domainUpstreamChord", "domainDownstreamChord", "domainTopChord"):
        _positive(mesh.get(field), f"mesh.{field}")
    alpha = mesh.get("angleDeg")
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not math.isfinite(float(alpha)):
        raise ManifestError("mesh.angleDeg must be finite")
    if abs(float(alpha)) > 30:
        raise ManifestError("mesh.angleDeg must stay within +/-30 degrees")
    sizing = _mapping(mesh.get("sizing"), "mesh.sizing")
    _positive(sizing.get("surfaceSizeM"), "mesh.sizing.surfaceSizeM")
    _positive(sizing.get("farfieldSizeM"), "mesh.sizing.farfieldSizeM")
    boundary_layer = _mapping(sizing.get("boundaryLayer"), "mesh.sizing.boundaryLayer")
    if not isinstance(boundary_layer.get("enabled"), bool):
        raise ManifestError("mesh.sizing.boundaryLayer.enabled must be boolean")
    _positive(boundary_layer.get("firstLayerM"), "mesh.sizing.boundaryLayer.firstLayerM")
    growth = _positive(boundary_layer.get("growthRatio"), "mesh.sizing.boundaryLayer.growthRatio")
    if growth <= 1.0:
        raise ManifestError("mesh.sizing.boundaryLayer.growthRatio must be > 1")
    count = boundary_layer.get("layerCount")
    if isinstance(count, bool) or not isinstance(count, int) or not 3 <= count <= 50:
        raise ManifestError("mesh.sizing.boundaryLayer.layerCount must be an integer from 3 through 50")

    flow = _mapping(root.get("flow"), "flow")
    for field in ("velocityMps", "densityKgM3", "viscosityPaS", "temperatureK"):
        _positive(flow.get(field), f"flow.{field}")
    if flow.get("model") != "k-omega-sst":
        raise ManifestError("flow.model must be k-omega-sst for the v1 profile")
    _positive(flow.get("turbulenceIntensity"), "flow.turbulenceIntensity")
    if float(flow["turbulenceIntensity"]) > 1.0:
        raise ManifestError("flow.turbulenceIntensity is a fraction and must be <= 1")
    _positive(flow.get("turbulentViscosityRatio"), "flow.turbulentViscosityRatio")
    if flow.get("groundMotion") != "moving-freestream":
        raise ManifestError("flow.groundMotion must be moving-freestream for the v1 ground-effect profile")

    reference = _mapping(root.get("reference"), "reference")
    for field in ("areaM2", "lengthM"):
        _positive(reference.get(field), f"reference.{field}")
    axes = _mapping(reference.get("axes"), "reference.axes")
    if axes.get("x") != "freestream-positive" or axes.get("y") != "up-positive":
        raise ManifestError("reference.axes must define x=freestream-positive and y=up-positive")
    if reference.get("rawForceConvention") != "force-on-body-by-fluid":
        raise ManifestError("reference.rawForceConvention must be force-on-body-by-fluid")
    if reference.get("coefficientConvention") != "Cd=Fx/(qA);C_DF=-Fy/(qA)":
        raise ManifestError("reference coefficient convention is not the approved v1 convention")

    iterations = _mapping(root.get("iterations"), "iterations")
    for field in ("warmup", "secondOrder", "sampleEvery", "extensionChunk", "hardMaximum"):
        value = iterations.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ManifestError(f"iterations.{field} must be a positive integer")
    requested = iterations["warmup"] + iterations["secondOrder"]
    if requested > iterations["hardMaximum"]:
        raise ManifestError("requested iterations exceed iterations.hardMaximum")
    if not isinstance(iterations.get("autoExtend"), bool):
        raise ManifestError("iterations.autoExtend must be boolean")

    gates = _mapping(root.get("convergence"), "convergence")
    residuals = _mapping(gates.get("residualMax"), "convergence.residualMax")
    for key in ("continuity", "x-velocity", "y-velocity", "k", "omega"):
        _positive(residuals.get(key), f"convergence.residualMax.{key}")
    _positive(gates.get("massImbalanceRatioMax"), "convergence.massImbalanceRatioMax")
    _positive(gates.get("forcePlateauRelativeRangeMax"), "convergence.forcePlateauRelativeRangeMax")
    min_samples = gates.get("forcePlateauMinSamples")
    if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 3:
        raise ManifestError("convergence.forcePlateauMinSamples must be an integer >= 3")

    artifacts = _mapping(root.get("artifacts"), "artifacts")
    required = artifacts.get("required")
    approved = {
        "report.json", "summary.html", "residuals.csv", "forces.csv", "mesh-quality.json",
        "vector.png", "velocity-contour.png", "pressure-contour.png", "case.cas.h5", "case.dat.h5",
    }
    if not isinstance(required, list) or not required or any(item not in approved for item in required):
        raise ManifestError("artifacts.required contains an unknown or empty artifact contract")
    for mandatory in ("report.json", "residuals.csv", "forces.csv", "mesh-quality.json"):
        if mandatory not in required:
            raise ManifestError(f"artifacts.required must include {mandatory}")

    authority = _mapping(root.get("authority"), "authority")
    values = [authority.get(key) for key in ("manualBaselineId", "manualCd", "manualCDF", "manualTolerance")]
    if any(value is not None for value in values):
        if not isinstance(values[0], str) or not values[0].strip():
            raise ManifestError("authority.manualBaselineId is required when a manual baseline is supplied")
        for key, value in zip(("manualCd", "manualCDF", "manualTolerance"), values[1:]):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ManifestError(f"authority.{key} must be finite when a manual baseline is supplied")
        if float(values[3]) <= 0:
            raise ManifestError("authority.manualTolerance must be positive")


def manifest_hash(data: dict[str, Any]) -> str:
    return canonical_hash(data)


def resolve_airfoil_path(data: dict[str, Any], manifest_root: Path) -> Path | None:
    airfoil = data["mesh"]["airfoil"]
    if airfoil["sourceType"] != "selig-dat":
        return None
    return resolve_under(
        manifest_root,
        safe_relative_path(airfoil["path"], field="mesh.airfoil.path"),
        field="mesh.airfoil.path",
    )
