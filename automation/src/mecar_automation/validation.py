from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from .errors import ValidationError
from .util import canonical_json_bytes, load_json, require_safe_component, sha256_bytes


MANIFEST_SCHEMA_VERSION = "1.0.0"
PROFILE_SCHEMA_VERSION = "1.0.0"
SUPPORTED_ADAPTERS = {"dummy", "mapdl_v211", "fluent_v211"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object")
    return value


def _require_number(value: Any, field: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValidationError(f"{field} must be finite")
    if minimum is not None and numeric < minimum:
        raise ValidationError(f"{field} must be at least {minimum}")
    return numeric


def validate_manifest(value: dict[str, Any]) -> dict[str, Any]:
    allowed_top = {
        "schema_version", "submission_id", "profile", "adapter", "timeout_sec", "parameters",
        "inputs", "resources", "notification",
    }
    unknown = set(value) - allowed_top
    if unknown:
        raise ValidationError(f"Unknown manifest fields: {sorted(unknown)}")
    if value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValidationError(f"schema_version must be {MANIFEST_SCHEMA_VERSION}")
    submission_id = require_safe_component(value.get("submission_id"), "submission_id")
    profile = _require_object(value.get("profile"), "profile")
    if set(profile) != {"id", "version"}:
        raise ValidationError("profile must contain exactly id and version")
    profile_id = require_safe_component(profile.get("id"), "profile.id")
    profile_version = require_safe_component(profile.get("version"), "profile.version")
    adapter = value.get("adapter")
    if adapter not in SUPPORTED_ADAPTERS:
        raise ValidationError(f"adapter must be one of {sorted(SUPPORTED_ADAPTERS)}")
    timeout_sec = _require_number(value.get("timeout_sec", 3600), "timeout_sec", 0.05)
    if timeout_sec > 7 * 24 * 3600:
        raise ValidationError("timeout_sec exceeds the seven-day safety ceiling")
    parameters = _require_object(value.get("parameters", {}), "parameters")
    if any(str(key).startswith("_") for key in parameters):
        raise ValidationError("parameters may not contain private keys")
    inputs = value.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) > 64:
        raise ValidationError("inputs must be an array with at most 64 entries")
    for index, item in enumerate(inputs):
        item = _require_object(item, f"inputs[{index}]")
        if set(item) - {"path", "sha256"}:
            raise ValidationError(f"inputs[{index}] contains unknown fields")
        path = item.get("path")
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValidationError(f"inputs[{index}].path must be a safe relative path")
        checksum = item.get("sha256")
        if checksum is not None and (not isinstance(checksum, str) or not _SHA256.fullmatch(checksum)):
            raise ValidationError(f"inputs[{index}].sha256 must be lowercase SHA-256")
    resources = _require_object(value.get("resources", {}), "resources")
    if set(resources) - {"cpu", "memory_mb", "licenses"}:
        raise ValidationError("resources contains unknown fields")
    if isinstance(resources.get("cpu", 1), bool) or not isinstance(resources.get("cpu", 1), int):
        raise ValidationError("resources.cpu must be an integer")
    if isinstance(resources.get("memory_mb", 256), bool) or not isinstance(resources.get("memory_mb", 256), int):
        raise ValidationError("resources.memory_mb must be an integer")
    cpu = int(_require_number(resources.get("cpu", 1), "resources.cpu", 1))
    memory_mb = int(_require_number(resources.get("memory_mb", 256), "resources.memory_mb", 1))
    licenses = resources.get("licenses", {})
    if not isinstance(licenses, dict):
        raise ValidationError("resources.licenses must be an object")
    for name, count in licenses.items():
        require_safe_component(name, "resources.licenses key")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValidationError("license counts must be non-negative integers")
    notification = _require_object(value.get("notification", {}), "notification")
    if set(notification) - {"recipients"}:
        raise ValidationError("notification contains unknown fields")
    recipients = notification.get("recipients", [])
    if not isinstance(recipients, list) or len(recipients) > 20:
        raise ValidationError("notification.recipients must contain at most 20 addresses")
    for address in recipients:
        if not isinstance(address, str) or not _EMAIL.fullmatch(address):
            raise ValidationError(f"Invalid recipient address: {address!r}")
    if len({address.lower() for address in recipients}) != len(recipients):
        raise ValidationError("notification.recipients contains duplicates")
    normalized = dict(value)
    normalized["submission_id"] = submission_id
    normalized["profile"] = {"id": profile_id, "version": profile_version}
    normalized["timeout_sec"] = timeout_sec
    normalized["parameters"] = parameters
    normalized["inputs"] = inputs
    normalized["resources"] = {"cpu": cpu, "memory_mb": memory_mb, "licenses": licenses}
    normalized["notification"] = {"recipients": recipients}
    return normalized


def manifest_hash(value: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(validate_manifest(value)))


def validate_profile(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ValidationError(f"profile schema_version must be {PROFILE_SCHEMA_VERSION}")
    profile_id = require_safe_component(value.get("profile_id"), "profile_id")
    version = require_safe_component(value.get("version"), "version")
    adapter = value.get("adapter")
    if adapter not in SUPPORTED_ADAPTERS:
        raise ValidationError(f"Unsupported profile adapter: {adapter!r}")
    if not isinstance(value.get("enabled"), bool):
        raise ValidationError("profile enabled must be boolean")
    settings = _require_object(value.get("settings", {}), "settings")
    if adapter in {"mapdl_v211", "fluent_v211"}:
        if value.get("ansys_release") != "211":
            raise ValidationError("ANSYS adapter profiles must pin ansys_release to 211")
        if not isinstance(value.get("external_execution_enabled"), bool):
            raise ValidationError("external_execution_enabled must be boolean")
        for field in ("executable", "executable_sha256", "approved_input", "approved_input_sha256"):
            if not isinstance(settings.get(field), str) or not settings[field]:
                raise ValidationError(f"settings.{field} is required")
        if not Path(settings["executable"]).is_absolute() or not Path(settings["approved_input"]).is_absolute():
            raise ValidationError("External executable and approved input must use absolute paths")
        if not _SHA256.fullmatch(settings["approved_input_sha256"]):
            raise ValidationError("settings.approved_input_sha256 must be lowercase SHA-256")
        if not _SHA256.fullmatch(settings["executable_sha256"]):
            raise ValidationError("settings.executable_sha256 must be lowercase SHA-256")
        assets = settings.get("approved_assets", [])
        if not isinstance(assets, list) or len(assets) > 32:
            raise ValidationError("settings.approved_assets must contain at most 32 entries")
        targets: set[str] = set()
        for index, asset in enumerate(assets):
            asset = _require_object(asset, f"settings.approved_assets[{index}]")
            if set(asset) != {"source", "target", "sha256"}:
                raise ValidationError("Each approved asset must contain exactly source, target and sha256")
            if (
                not isinstance(asset["source"], str)
                or not asset["source"]
                or not Path(asset["source"]).is_absolute()
            ):
                raise ValidationError("Approved asset source must be an absolute path")
            target = asset["target"]
            if (
                not isinstance(target, str)
                or not target
                or Path(target).is_absolute()
                or ".." in Path(target).parts
                or target.casefold() in targets
            ):
                raise ValidationError("Approved asset target must be a unique safe relative path")
            if not isinstance(asset["sha256"], str) or not _SHA256.fullmatch(asset["sha256"]):
                raise ValidationError("Approved asset sha256 must be lowercase SHA-256")
            targets.add(target.casefold())
        mandatory_outputs = settings.get("mandatory_outputs")
        if not isinstance(mandatory_outputs, list) or not mandatory_outputs or len(mandatory_outputs) > 64:
            raise ValidationError("settings.mandatory_outputs must contain 1 to 64 paths")
        output_keys: set[str] = set()
        for output in mandatory_outputs:
            if (
                not isinstance(output, str)
                or not output
                or Path(output).is_absolute()
                or ".." in Path(output).parts
                or output.casefold() in output_keys
            ):
                raise ValidationError("Mandatory outputs must be unique safe relative paths")
            output_keys.add(output.casefold())
        if adapter == "fluent_v211" and settings.get("dimension_precision") not in {"2ddp", "3ddp"}:
            raise ValidationError("Fluent dimension_precision must be 2ddp or 3ddp")
        max_timeout = _require_number(settings.get("max_timeout_sec"), "settings.max_timeout_sec", 0.05)
        if max_timeout > 7 * 24 * 3600:
            raise ValidationError("settings.max_timeout_sec exceeds the seven-day safety ceiling")
        trusted_resources = _require_object(value.get("resources"), "profile resources")
        if set(trusted_resources) != {"cpu", "memory_mb", "licenses"}:
            raise ValidationError("External profile resources must contain exactly cpu, memory_mb and licenses")
        for field in ("cpu", "memory_mb"):
            if (
                isinstance(trusted_resources[field], bool)
                or not isinstance(trusted_resources[field], int)
                or trusted_resources[field] < 1
            ):
                raise ValidationError(f"profile resources.{field} must be a positive integer")
        trusted_licenses = _require_object(trusted_resources["licenses"], "profile resources.licenses")
        if not trusted_licenses:
            raise ValidationError("External profiles must reserve at least one trusted license feature")
        for feature, count in trusted_licenses.items():
            require_safe_component(feature, "profile license feature")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise ValidationError("External profile license counts must be positive integers")
    normalized = dict(value)
    normalized["profile_id"] = profile_id
    normalized["version"] = version
    normalized["settings"] = settings
    return normalized


class ProfileRegistry:
    def __init__(self, root: Path):
        self.root = root

    def resolve(self, profile_id: str, version: str) -> dict[str, Any]:
        require_safe_component(profile_id, "profile.id")
        require_safe_component(version, "profile.version")
        path = self.root / f"{profile_id}-{version}.json"
        profile = validate_profile(load_json(path))
        if profile["profile_id"] != profile_id or profile["version"] != version:
            raise ValidationError("Profile filename and identity do not match")
        return profile
