from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any, Iterable


FLOAT = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
RESIDUAL_RE = re.compile(
    rf"^[ \t]*(\d+)[ \t]+({FLOAT})[ \t]+({FLOAT})[ \t]+({FLOAT})[ \t]+({FLOAT})[ \t]+({FLOAT})(?:[ \t]|$)",
    re.MULTILINE,
)
VECTOR_NET_RE = re.compile(
    rf"^Net\s+\(({FLOAT})\s+({FLOAT})\s+({FLOAT})\)\s+"
    rf"\(({FLOAT})\s+({FLOAT})\s+({FLOAT})\)\s+"
    rf"\(({FLOAT})\s+({FLOAT})\s+({FLOAT})\)",
    re.MULTILINE,
)
MASS_ROW_RE = re.compile(rf"^\s*(inlet|outlet|Net)\s+({FLOAT})\s*$", re.MULTILINE)
FATAL_PATTERNS = {
    "tui-invalid-command": re.compile(r"invalid command", re.IGNORECASE),
    "floating-point-exception": re.compile(r"floating point exception", re.IGNORECASE),
    "mesh-check-failed": re.compile(r"Mesh check failed", re.IGNORECASE),
    "license-error": re.compile(r"license.*(?:unavailable|checkout failed|denied)", re.IGNORECASE),
    "fluent-error": re.compile(r"^Error(?: at [^:]+)?:", re.IGNORECASE | re.MULTILINE),
}


def _force_after_marker(text: str, marker: str) -> dict[str, float] | None:
    index = text.find(marker)
    if index < 0:
        return None
    next_marker = text.find("; MECAR_", index + len(marker))
    segment = text[index : next_marker if next_marker >= 0 else len(text)]
    match = VECTOR_NET_RE.search(segment)
    if not match:
        return None
    return {"fxN": float(match.group(7)), "fyN": float(match.group(8)), "fzN": float(match.group(9))}


def parse_transcript_text(text: str, manifest: dict[str, Any]) -> dict[str, Any]:
    residual_rows = [
        {
            "iteration": int(match.group(1)),
            "continuity": float(match.group(2)),
            "x-velocity": float(match.group(3)),
            "y-velocity": float(match.group(4)),
            "k": float(match.group(5)),
            "omega": float(match.group(6)),
        }
        for match in RESIDUAL_RE.finditer(text)
    ]
    # Repeated /solve/iterate calls print the previous iteration once. Keep the
    # last occurrence for each monotonically reported iteration number.
    residual_by_iteration = {row["iteration"]: row for row in residual_rows}
    residuals = [residual_by_iteration[key] for key in sorted(residual_by_iteration)]

    force_samples = []
    for marker in re.finditer(r"; MECAR_FORCE_SAMPLE iteration=(\d+)", text):
        force = _force_after_marker(text[marker.start() :], marker.group(0))
        if force:
            force_samples.append({"iteration": int(marker.group(1)), "dragN": force["fxN"], "liftN": force["fyN"]})
    raw_force = _force_after_marker(text, "; MECAR_FINAL_FORCE")
    mass_segment_start = text.rfind("; MECAR_MASS_FLOW")
    mass_rows: dict[str, float] = {}
    if mass_segment_start >= 0:
        for match in MASS_ROW_RE.finditer(text[mass_segment_start:]):
            mass_rows[match.group(1).lower()] = float(match.group(2))
    inlet = mass_rows.get("inlet")
    outlet = mass_rows.get("outlet")
    net = mass_rows.get("net")
    if all(value is not None and math.isfinite(value) for value in (inlet, outlet, net)):
        mass_ratio = abs(float(net)) / max(abs(float(inlet)), abs(float(outlet)), 1e-30)
    else:
        mass_ratio = None

    coefficient = None
    if raw_force:
        density = float(manifest["flow"]["densityKgM3"])
        velocity = float(manifest["flow"]["velocityMps"])
        area = float(manifest["reference"]["areaM2"])
        denominator = 0.5 * density * velocity**2 * area
        coefficient = {"Cd": raw_force["fxN"] / denominator, "C_DF": -raw_force["fyN"] / denominator}
    fatal = [name for name, pattern in FATAL_PATTERNS.items() if pattern.search(text)]
    return {
        "completedMarker": "; MECAR_RUN_COMPLETE" in text,
        "fatalDiagnostics": fatal,
        "residuals": residuals,
        "latestResidual": residuals[-1] if residuals else None,
        "forceSamples": force_samples,
        "rawForce": raw_force,
        "coefficient": coefficient,
        "massFlowKgS": {"inlet": inlet, "outlet": outlet, "net": net},
        "massImbalanceRatio": mass_ratio,
        "definitions": {
            "rawForceConvention": manifest["reference"]["rawForceConvention"],
            "axes": manifest["reference"]["axes"],
            "coefficientConvention": manifest["reference"]["coefficientConvention"],
            "dynamicPressurePa": 0.5 * float(manifest["flow"]["densityKgM3"]) * float(manifest["flow"]["velocityMps"]) ** 2,
            "referenceAreaM2": float(manifest["reference"]["areaM2"]),
            "referenceLengthM": float(manifest["reference"]["lengthM"]),
        },
    }


def merge_parsed(values: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(values)
    if not items:
        raise ValueError("at least one parsed transcript is required")
    merged = dict(items[-1])
    residuals: dict[int, dict[str, Any]] = {}
    force_samples: dict[int, dict[str, Any]] = {}
    fatal: list[str] = []
    for item in items:
        for row in item.get("residuals") or []:
            residuals[int(row["iteration"])] = row
        for row in item.get("forceSamples") or []:
            force_samples[int(row["iteration"])] = row
        fatal.extend(item.get("fatalDiagnostics") or [])
    merged["residuals"] = [residuals[key] for key in sorted(residuals)]
    merged["latestResidual"] = merged["residuals"][-1] if merged["residuals"] else None
    merged["forceSamples"] = [force_samples[key] for key in sorted(force_samples)]
    merged["fatalDiagnostics"] = sorted(set(fatal))
    merged["completedMarker"] = all(bool(item.get("completedMarker")) for item in items)
    return merged


def parse_transcripts(paths: Iterable[Path], manifest: dict[str, Any]) -> dict[str, Any]:
    parsed = [parse_transcript_text(path.read_text(encoding="utf-8", errors="replace"), manifest) for path in paths]
    return merge_parsed(parsed)


def write_monitor_csvs(parsed: dict[str, Any], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    with (reports_dir / "residuals.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["iteration", "continuity", "x-velocity", "y-velocity", "k", "omega"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(parsed.get("residuals") or [])
    with (reports_dir / "forces.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["iteration", "dragN", "liftN"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(parsed.get("forceSamples") or [])
