from __future__ import annotations

import unittest
from pathlib import Path

from mecar_fluent2d.journal import build_journal
from mecar_fluent2d.manifest import load_manifest


ROOT = Path(__file__).resolve().parents[1]


class JournalTests(unittest.TestCase):
    def test_v211_journal_is_template_free_and_runtime_relative(self) -> None:
        manifest, _ = load_manifest(ROOT / "config" / "golden-naca0012.json")
        journal = build_journal(manifest, Path(r"C:\MECarRuntime\fluent\cases\fixture"))
        self.assertIn('/file/set-tui-version "21.1"', journal)
        self.assertIn("/file/read-case", journal)
        self.assertIn("input/mesh.msh", journal.replace("\\", "/"))
        self.assertNotIn("template.cas", journal.lower())
        self.assertNotIn("26.1", journal)
        self.assertIn("motion-bc-moving", journal)


if __name__ == "__main__":
    unittest.main()

