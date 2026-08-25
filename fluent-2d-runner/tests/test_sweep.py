from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mecar_fluent2d.sweep import generate_sweep_manifests


ROOT = Path(__file__).resolve().parents[1]


class SweepTests(unittest.TestCase):
    def test_source_manifest_covers_all_planned_profiles(self) -> None:
        plan = json.loads((ROOT / "config" / "sweep-plan.example.json").read_text(encoding="utf-8"))
        sources = json.loads((ROOT / "sources" / "airfoils.json").read_text(encoding="utf-8"))
        planned_ids = {profile["id"] for profile in plan["profiles"]}
        recorded = {profile["id"]: profile for profile in sources["profiles"]}
        self.assertTrue(planned_ids.issubset(recorded))
        self.assertEqual(recorded["NACA6412"]["status"], "available-procedural")
        self.assertEqual(recorded["NACA6409"]["status"], "available-procedural")
        self.assertEqual(recorded["S1223"]["status"], "blocked-missing-approved-source")
        self.assertEqual(recorded["E423"]["status"], "blocked-missing-approved-source")

    def test_plan_generates_available_profiles_and_blocks_missing_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = generate_sweep_manifests(
                ROOT / "config" / "golden-naca0012.json",
                ROOT / "config" / "sweep-plan.example.json",
                temporary,
            )
            self.assertEqual(result["expectedCaseCount"], 168)
            self.assertEqual(result["generatedCaseCount"], 84)
            self.assertEqual(result["blockedCaseCount"], 84)
            self.assertFalse(result["complete"])


if __name__ == "__main__":
    unittest.main()
