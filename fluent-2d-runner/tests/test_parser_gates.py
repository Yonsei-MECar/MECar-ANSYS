from __future__ import annotations

import unittest
from pathlib import Path

from mecar_fluent2d.gates import evaluate_engineering_gates
from mecar_fluent2d.manifest import load_manifest
from mecar_fluent2d.parser import parse_transcript_text


ROOT = Path(__file__).resolve().parents[1]


class ParserGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest, _ = load_manifest(ROOT / "config" / "golden-naca0012.json")

    def test_raw_total_force_and_sign_convention(self) -> None:
        text = """
400 9e-6 8e-7 7e-7 6e-6 5e-6 0:00:01 0
; MECAR_FORCE_SAMPLE iteration=400
Net (1 2 0) (2 3 0) (10 -20 0) (0 0 0) (0 0 0) (0 0 0)
; MECAR_FINAL_FORCE
Net (1 2 0) (2 3 0) (10 -20 0) (0 0 0) (0 0 0) (0 0 0)
; MECAR_MASS_FLOW
inlet 10
outlet -9.999
Net 0.001
; MECAR_RUN_COMPLETE
"""
        parsed = parse_transcript_text(text, self.manifest)
        self.assertEqual(parsed["rawForce"]["fxN"], 10.0)
        self.assertEqual(parsed["rawForce"]["fyN"], -20.0)
        self.assertGreater(parsed["coefficient"]["C_DF"], 0.0)
        self.assertAlmostEqual(parsed["massImbalanceRatio"], 0.0001)

    def test_csv_presence_cannot_replace_missing_evidence(self) -> None:
        parsed = parse_transcript_text("; MECAR_RUN_COMPLETE\n", self.manifest)
        required = set(self.manifest["artifacts"]["required"])
        gate = evaluate_engineering_gates(self.manifest, parsed, present_artifacts=required)
        self.assertFalse(gate["passed"])
        self.assertFalse(gate["checks"]["meshQuality"]["passed"])
        self.assertFalse(gate["checks"]["residuals"]["continuity"]["passed"])
        self.assertFalse(gate["checks"]["finiteForcesAndCoefficients"]["passed"])

    def test_force_plateau_requires_drag_and_downforce_stability(self) -> None:
        samples = [
            {"iteration": index, "dragN": 1.0, "liftN": lift}
            for index, lift in enumerate((-10.0, -12.0, -8.0, -11.0, -9.0), start=1)
        ]
        parsed = {
            "latestResidual": {
                "continuity": 1e-6,
                "x-velocity": 1e-7,
                "y-velocity": 1e-7,
                "k": 1e-6,
                "omega": 1e-6,
            },
            "massImbalanceRatio": 1e-8,
            "forceSamples": samples,
            "rawForce": {"fxN": 1.0, "fyN": -10.0},
            "coefficient": {"Cd": 0.1, "C_DF": 1.0},
        }
        gate = evaluate_engineering_gates(
            self.manifest,
            parsed,
            present_artifacts=set(self.manifest["artifacts"]["required"]),
            mesh_quality={"passed": True, "gmshVersion": "4.13.1", "generatorVersion": "mecar-gmsh2d/v1"},
        )
        plateau = gate["checks"]["forcePlateau"]
        self.assertEqual(plateau["dragRelativeRange"], 0.0)
        self.assertGreater(plateau["liftRelativeRange"], plateau["limit"])
        self.assertFalse(plateau["passed"])
        self.assertFalse(gate["passed"])


if __name__ == "__main__":
    unittest.main()
