from __future__ import annotations

import unittest

from mecar_fluent2d.mesh import naca4_points


class MeshTests(unittest.TestCase):
    def test_naca_generator_is_deterministic_and_closed_by_writer(self) -> None:
        first = naca4_points("NACA0012")
        second = naca4_points("NACA0012")
        self.assertEqual(first, second)
        self.assertGreater(len(first), 200)
        self.assertAlmostEqual(min(x for x, _ in first), 0.0, places=10)
        self.assertAlmostEqual(max(x for x, _ in first), 1.0, places=10)


if __name__ == "__main__":
    unittest.main()

