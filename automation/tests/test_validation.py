from __future__ import annotations

import unittest

from mecar_automation.errors import ValidationError
from mecar_automation.util import load_json
from mecar_automation.validation import validate_manifest, validate_profile

from .support import EXAMPLES, PACKAGE_ROOT, PROFILES


class ValidationTests(unittest.TestCase):
    def test_valid_manifest_examples(self) -> None:
        for name in ("valid-dummy.json", "valid-mapdl-v211.json", "valid-fluent-v211.json"):
            with self.subTest(name=name):
                validate_manifest(load_json(EXAMPLES / "manifests" / name))

    def test_invalid_manifest_examples(self) -> None:
        for name in ("invalid-dummy.json", "invalid-mapdl-v211.json", "invalid-fluent-v211.json"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_manifest(load_json(EXAMPLES / "manifests" / name))

    def test_valid_profiles(self) -> None:
        paths = list(PROFILES.glob("*.json")) + list(
            (PACKAGE_ROOT / "src" / "mecar_automation" / "default_profiles").glob("*.json")
        )
        for path in paths:
            with self.subTest(path=path.name):
                validate_profile(load_json(path))

    def test_invalid_external_profile_examples(self) -> None:
        for path in (EXAMPLES / "profiles").glob("invalid-*.json"):
            with self.subTest(path=path.name), self.assertRaises(ValidationError):
                validate_profile(load_json(path))

    def test_duplicate_json_keys_rejected(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_json(path)

    def test_nonfinite_numbers_and_unknown_fields_rejected(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nan.json"
            path.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_json(path)
        value = load_json(EXAMPLES / "manifests" / "valid-dummy.json")
        value["command"] = "unapproved"
        with self.assertRaises(ValidationError):
            validate_manifest(value)


if __name__ == "__main__":
    unittest.main()
