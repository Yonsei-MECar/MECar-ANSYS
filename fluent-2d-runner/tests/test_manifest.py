from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from mecar_fluent2d.errors import InputError, ManifestError
from mecar_fluent2d.manifest import load_manifest, validate_manifest


ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_golden_manifest_is_valid(self) -> None:
        manifest, _ = load_manifest(ROOT / "config" / "golden-naca0012.json")
        self.assertEqual(manifest["solver"]["release"], "2021 R1")

    def test_missing_approved_s1223_fails_closed(self) -> None:
        with self.assertRaises((InputError, ManifestError)):
            load_manifest(ROOT / "config" / "missing-s1223.example.json")

    def test_absolute_airfoil_path_is_rejected(self) -> None:
        manifest, path = load_manifest(ROOT / "config" / "golden-naca0012.json")
        changed = copy.deepcopy(manifest)
        changed["mesh"]["airfoil"] = {
            "id": "TEST",
            "sourceType": "selig-dat",
            "path": "C:/outside/profile.dat",
            "sha256": "0" * 64,
            "source": "fixture",
            "license": "fixture",
        }
        with self.assertRaises(ManifestError):
            validate_manifest(changed, path.parent)

    def test_baseline_fields_are_all_or_none(self) -> None:
        manifest, path = load_manifest(ROOT / "config" / "golden-naca0012.json")
        changed = copy.deepcopy(manifest)
        changed["authority"]["manualBaselineId"] = "gui-1"
        with self.assertRaises(ManifestError):
            validate_manifest(changed, path.parent)


if __name__ == "__main__":
    unittest.main()
