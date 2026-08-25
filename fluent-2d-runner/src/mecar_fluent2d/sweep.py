from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .errors import ManifestError
from .manifest import load_manifest, validate_manifest
from .util import atomic_write_json


def _angle_tag(value: float) -> str:
    sign = "p" if value >= 0 else "m"
    return f"{sign}{abs(value):04.1f}".replace(".", "")


def generate_sweep_manifests(
    base_manifest_path: str | Path,
    plan_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    base, _ = load_manifest(base_manifest_path)
    plan_file = Path(plan_path).resolve()
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    if plan.get("schemaVersion") != "mecar.fluent2d.sweep-plan/v1":
        raise ManifestError("unsupported sweep plan schemaVersion")
    profiles = plan.get("profiles")
    heights = plan.get("heightsMm")
    angles = plan.get("anglesDeg")
    if not isinstance(profiles, list) or not isinstance(heights, list) or not isinstance(angles, list):
        raise ManifestError("sweep plan profiles, heightsMm, and anglesDeg must be arrays")
    output = Path(output_root).resolve()
    manifests_dir = output / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    blocked = []
    for profile in profiles:
        for height_mm in heights:
            for angle_deg in angles:
                candidate = copy.deepcopy(base)
                profile_id = str(profile.get("id", "unknown"))
                case_id = f"{profile_id.lower()}-h{int(height_mm):03d}-a{_angle_tag(float(angle_deg))}"
                candidate["caseId"] = case_id
                candidate["mesh"]["airfoil"] = copy.deepcopy(profile)
                candidate["mesh"]["heightM"] = float(height_mm) / 1000.0
                candidate["mesh"]["angleDeg"] = float(angle_deg)
                path = manifests_dir / f"{case_id}.json"
                try:
                    validate_manifest(candidate, manifests_dir)
                except Exception as exc:
                    blocked.append({"caseId": case_id, "profile": profile_id, "reason": f"{type(exc).__name__}: {exc}"})
                    continue
                atomic_write_json(path, candidate)
                generated.append(path.name)
    expected = len(profiles) * len(heights) * len(angles)
    summary = {
        "schemaVersion": "mecar.fluent2d.sweep-generation/v1",
        "expectedCaseCount": expected,
        "generatedCaseCount": len(generated),
        "blockedCaseCount": len(blocked),
        "complete": len(generated) == expected,
        "manifestsDirectory": str(manifests_dir),
        "generated": generated,
        "blocked": blocked,
    }
    atomic_write_json(output / "sweep-generation.json", summary)
    return summary
