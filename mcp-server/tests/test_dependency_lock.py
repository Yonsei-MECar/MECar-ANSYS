import importlib.metadata
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECT_PINS = {
    "mcp": "1.29.0",
    "ansys-mapdl-core": "0.73.2",
}
TOOL_PINS = {
    "hatchling": "1.27.0",
    "pytest": "8.4.2",
}
PACKAGE_VERSION = "0.1.1"


def test_release_version_is_consistent():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_init = (ROOT / "src" / "ansys_mcp_server" / "__init__.py").read_text(
        encoding="utf-8"
    )
    build_script = (ROOT / "build-package.ps1").read_text(encoding="utf-8")
    readme = (ROOT / "README_KO.md").read_text(encoding="utf-8")
    assert f'version = "{PACKAGE_VERSION}"' in pyproject
    assert f'__version__ = "{PACKAGE_VERSION}"' in package_init
    assert f"[string]$Version = '{PACKAGE_VERSION}'" in build_script
    assert f"mecar-ansys-mcp-server-{PACKAGE_VERSION}.zip" in readme


def test_pyproject_uses_exact_validated_versions():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name, version in {**DIRECT_PINS, **TOOL_PINS}.items():
        assert f'"{name}=={version}"' in pyproject
    for name in DIRECT_PINS:
        for operator in (">=", "<=", "~=", "!=", ">", "<"):
            assert f'"{name}{operator}' not in pyproject


def test_lock_contains_exact_pins_and_hashes():
    lock = (ROOT / "requirements.lock.txt").read_text(encoding="utf-8")
    for name, version in {**DIRECT_PINS, **TOOL_PINS}.items():
        assert re.search(rf"(?m)^{re.escape(name)}=={re.escape(version)}(?:\s|\\)", lock)
    assert "--hash=sha256:" in lock
    assert "--python-version 3.10" in lock
    assert "--python-platform x86_64-pc-windows-msvc" in lock


def test_installer_enforces_lock_without_online_reresolution():
    installer = (ROOT / "install.ps1").read_text(encoding="utf-8")
    assert "--require-hashes" in installer
    assert "--only-binary=:all:" in installer
    assert "--no-deps" in installer
    assert "--no-build-isolation" in installer
    assert "--upgrade pip" not in installer
    assert "--no-index" in installer
    assert "verify_dependency_lock.py" in installer
    assert "pip check" in installer


def test_installed_direct_dependencies_match_validated_versions():
    for name, version in DIRECT_PINS.items():
        assert importlib.metadata.version(name) == version
