from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..errors import ExternalExecutionDisabled, ValidationError
from ..util import resolve_within, sha256_file


def stage_approved_input(
    profile: dict[str, Any],
    workdir: Path,
    target_name: str,
    *,
    external_execution_enabled: bool,
) -> tuple[Path, Path]:
    if not external_execution_enabled or not profile.get("external_execution_enabled", False):
        raise ExternalExecutionDisabled(
            "Both machine config and the approved v211 profile must explicitly enable external execution"
        )
    if profile.get("ansys_release") != "211":
        raise ValidationError("Only the explicitly pinned ANSYS release 211 port is supported")
    settings = profile["settings"]
    executable = Path(settings["executable"])
    approved_input = Path(settings["approved_input"])
    if not executable.is_absolute() or not executable.is_file():
        raise ValidationError("Configured ANSYS executable is not an existing absolute file")
    if not approved_input.is_absolute() or not approved_input.is_file():
        raise ValidationError("Configured approved solver input is not an existing absolute file")
    if sha256_file(executable) != settings["executable_sha256"]:
        raise ValidationError("Configured ANSYS executable checksum does not match the profile")
    if sha256_file(approved_input) != settings["approved_input_sha256"]:
        raise ValidationError("Approved solver input checksum does not match the profile")
    staged = resolve_within(workdir, target_name)
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(approved_input, staged)
    if sha256_file(staged) != settings["approved_input_sha256"]:
        raise ValidationError("Staged solver input checksum mismatch")
    used_targets = {target_name.casefold()}
    for asset in settings.get("approved_assets", []):
        source = Path(asset["source"])
        if not source.is_absolute() or not source.is_file():
            raise ValidationError("Configured approved solver asset is not an existing absolute file")
        if sha256_file(source) != asset["sha256"]:
            raise ValidationError("Approved solver asset checksum does not match the profile")
        target_key = asset["target"].casefold()
        if target_key in used_targets:
            raise ValidationError("Approved solver asset target collides with another staged input")
        used_targets.add(target_key)
        destination = resolve_within(workdir, asset["target"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if sha256_file(destination) != asset["sha256"]:
            raise ValidationError("Staged solver asset checksum mismatch")
    return executable, staged


def mandatory_artifacts(workdir: Path, settings: dict[str, Any]) -> tuple[tuple[str, Path], ...] | None:
    configured = settings.get("mandatory_outputs", [])
    if not isinstance(configured, list) or not configured:
        return None
    found: list[tuple[str, Path]] = []
    for index, relative in enumerate(configured):
        if not isinstance(relative, str):
            return None
        try:
            path = resolve_within(workdir, relative)
        except ValidationError:
            return None
        if not path.is_file() or path.stat().st_size == 0:
            return None
        found.append((f"mandatory_output_{index + 1}", path))
    return tuple(found)
