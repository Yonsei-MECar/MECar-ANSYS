from __future__ import annotations

import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from mecar_automation.adapters import FluentV211Adapter, MapdlV211Adapter
from mecar_automation.errors import ExternalExecutionDisabled, ResourceUnavailable
from mecar_automation.supervisor import ProcessResult, ResourceCapacity, ResourceGate, SingletonFileLock
from mecar_automation.util import load_json, sha256_file

from .support import PROFILES


class SupervisorAndPortTests(unittest.TestCase):
    def test_resource_and_license_requests_above_capacity_fail(self) -> None:
        gate = ResourceGate(ResourceCapacity(cpu=2, memory_mb=512, licenses={"solver": 1}))
        with self.assertRaises(ResourceUnavailable):
            with gate.reserve({"cpu": 3, "memory_mb": 64, "licenses": {}}):
                pass
        with self.assertRaises(ResourceUnavailable):
            with gate.reserve({"cpu": 1, "memory_mb": 64, "licenses": {"other": 1}}):
                pass

    def test_concurrent_reservations_are_serialized(self) -> None:
        gate = ResourceGate(ResourceCapacity(cpu=1, memory_mb=128))
        entered: list[str] = []
        release = threading.Event()

        def first() -> None:
            with gate.reserve({"cpu": 1, "memory_mb": 64, "licenses": {}}):
                entered.append("first")
                release.wait(1)

        worker = threading.Thread(target=first)
        worker.start()
        deadline = time.monotonic() + 1
        while "first" not in entered and time.monotonic() < deadline:
            time.sleep(0.01)
        with self.assertRaises(ResourceUnavailable):
            with gate.reserve({"cpu": 1, "memory_mb": 64, "licenses": {}}, wait_timeout=0.05):
                pass
        release.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())

    def test_dispatcher_singleton_lock_is_os_released(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dispatcher.lock"
            first = SingletonFileLock(path)
            second = SingletonFileLock(path)
            with first:
                with self.assertRaises(ResourceUnavailable):
                    with second:
                        pass
            with second:
                self.assertTrue(path.exists())

    def test_mapdl_and_fluent_ports_require_two_enable_switches(self) -> None:
        cases = [
            (MapdlV211Adapter(), PROFILES / "mapdl-v211-pending-1.0.0.json"),
            (FluentV211Adapter(), PROFILES / "fluent-v211-pending-1.0.0.json"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            for adapter, path in cases:
                profile = copy.deepcopy(load_json(path))
                profile["enabled"] = True
                profile["external_execution_enabled"] = True
                with self.subTest(adapter=adapter.name), self.assertRaises(ExternalExecutionDisabled):
                    adapter.prepare({}, profile, Path(directory) / adapter.name, external_execution_enabled=False)

    def test_approved_external_input_and_assets_are_checksum_staged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "ANSYS211.exe"
            master = root / "master.dat"
            asset = root / "material.inc"
            executable.write_bytes(b"approved executable")
            master.write_bytes(b"/input,material,inc")
            asset.write_bytes(b"material data")
            profile = {
                "adapter": "mapdl_v211",
                "enabled": True,
                "ansys_release": "211",
                "external_execution_enabled": True,
                "resources": {"cpu": 2, "memory_mb": 512, "licenses": {"ansys_structures": 1}},
                "settings": {
                    "executable": str(executable),
                    "executable_sha256": sha256_file(executable),
                    "approved_input": str(master),
                    "approved_input_sha256": sha256_file(master),
                    "approved_assets": [
                        {"source": str(asset), "target": "material.inc", "sha256": sha256_file(asset)}
                    ],
                    "mandatory_outputs": ["solver.out", "metrics.json"],
                    "max_timeout_sec": 60,
                },
            }
            workdir = root / "work"
            prepared = MapdlV211Adapter().prepare({}, profile, workdir, external_execution_enabled=True)
            self.assertEqual(Path(prepared.command[0]), executable)
            self.assertEqual((workdir / "approved_input.dat").read_bytes(), master.read_bytes())
            self.assertEqual((workdir / "material.inc").read_bytes(), asset.read_bytes())

    def test_mapdl_requires_structured_engineering_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            (workdir / "solver.out").write_text("NORMAL TERMINATION", encoding="utf-8")
            metrics = {
                "schema_version": "1.0.0",
                "solver_release": "211",
                "engineering_outcome": "PASSED",
                "checks": [{"name": "displacement", "passed": True}],
                "metrics": {"max_displacement_m": 0.001},
            }
            (workdir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            process = ProcessResult(0, False, False, 1.0, 1, {"mandatory_outputs": ["metrics.json"]})
            self.assertTrue(MapdlV211Adapter().evaluate(workdir, process).succeeded)
            metrics["checks"][0]["passed"] = False
            (workdir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            self.assertFalse(MapdlV211Adapter().evaluate(workdir, process).succeeded)

    def test_fluent_requires_convergence_and_finite_force_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            metrics = {
                "schema_version": "1.0.0",
                "solver_release": "211",
                "engineering_outcome": "PASSED",
                "metrics": {"drag_n": 100.0, "downforce_n": 200.0, "cd": 0.9, "cl": -1.8},
            }
            convergence = {
                "schema_version": "1.0.0",
                "converged": True,
                "force_monitor_stable": True,
                "mass_imbalance_percent": 0.1,
                "residuals": {"continuity": 0.0001},
            }
            (workdir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
            (workdir / "convergence.json").write_text(json.dumps(convergence), encoding="utf-8")
            process = ProcessResult(
                0,
                False,
                False,
                1.0,
                1,
                {"mandatory_outputs": ["metrics.json", "convergence.json"]},
            )
            self.assertTrue(FluentV211Adapter().evaluate(workdir, process).succeeded)
            convergence["converged"] = False
            (workdir / "convergence.json").write_text(json.dumps(convergence), encoding="utf-8")
            self.assertFalse(FluentV211Adapter().evaluate(workdir, process).succeeded)


if __name__ == "__main__":
    unittest.main()
