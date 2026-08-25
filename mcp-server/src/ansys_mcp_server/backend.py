from __future__ import annotations

import csv
import json
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings


class MapdlLaunchError(RuntimeError):
    """A classified MAPDL launch failure with a stable machine error code."""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


class AnsysBackend:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._mapdl: Any | None = None
        self._lock = threading.RLock()
        self._last_result: dict[str, Any] | None = None
        self._active_run_location: Path | None = None

    @property
    def connected(self) -> bool:
        return self._mapdl is not None

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "ansys_version": self.settings.ansys_version,
            "ansys_root": str(self.settings.ansys_root),
            "ansys_installed": self.settings.ansys_root.exists(),
            "workbench_exe": str(self.settings.workbench_exe),
            "workbench_available": self.settings.workbench_exe.is_file(),
            "mapdl_exe": str(self.settings.mapdl_exe),
            "mapdl_available": self.settings.mapdl_exe.is_file(),
            "work_root": str(self.settings.work_root),
            "run_location": str(self.settings.run_location),
            "raw_apdl_enabled": self.settings.allow_raw_apdl,
            "workbench_scripts_enabled": self.settings.allow_workbench_scripts,
        }

    def launch(self, *, nproc: int = 2, additional_switches: str = "") -> dict[str, Any]:
        if nproc < 1 or nproc > 64:
            raise ValueError("nproc must be between 1 and 64")
        with self._lock:
            if self._mapdl is not None:
                return {"connected": True, "reused": True}
            try:
                from ansys.mapdl.core import launch_mapdl
            except ImportError as exc:
                raise RuntimeError("PyMAPDL is not installed. Run install.ps1 first.") from exc
            if not self.settings.mapdl_exe.is_file():
                raise FileNotFoundError(f"MAPDL executable was not found: {self.settings.mapdl_exe}")
            self.settings.run_location.mkdir(parents=True, exist_ok=True)
            launch_location = self.settings.run_location / f"launch-{uuid.uuid4().hex}"
            launch_location.mkdir(parents=False, exist_ok=False)
            try:
                self._mapdl = launch_mapdl(
                    exec_file=str(self.settings.mapdl_exe),
                    mode="grpc",
                    run_location=str(launch_location),
                    nproc=nproc,
                    additional_switches=additional_switches,
                )
            except Exception as exc:
                code, hint = self._classify_launch_failure(exc, launch_location)
                raise MapdlLaunchError(code, hint) from exc
            self._active_run_location = launch_location
            return {
                "connected": True,
                "reused": False,
                "name": getattr(self._mapdl, "name", None),
                "run_location": str(launch_location),
            }

    def _classify_launch_failure(self, exc: Exception, launch_location: Path) -> tuple[str, str]:
        current_error = str(exc).lower()
        if "cannot specify both" in current_error or "configuration" in current_error:
            return "BAD_CONFIGURATION", f"MAPDL launcher configuration is invalid: {exc}"
        if "executable" in current_error and ("not found" in current_error or "does not exist" in current_error):
            return "EXECUTABLE_MISSING", f"MAPDL executable is unavailable: {self.settings.mapdl_exe}"
        output = launch_location / ".__tmp__.out"
        text = output.read_text(encoding="utf-8", errors="replace").lower() if output.is_file() else ""
        if "license server machine is down or not responding" in text or "license not available" in text:
            return (
                "LICENSE_UNAVAILABLE",
                f"The Ansys license server is unavailable; check the VPN/network and license settings. Log: {output}",
            )
        if "port" in text and "already" in text and "use" in text:
            return "PORT_IN_USE", f"The gRPC port may already be in use. Log: {output}"
        if output.is_file():
            return "MAPDL_START_FAILED", f"MAPDL failed to start; inspect the current launch log: {output}"
        return "MAPDL_START_FAILED", f"MAPDL failed to start: {exc}"

    def _launch_failure_hint(self) -> str | None:
        """Backward-compatible diagnostic for the active, current launch only."""
        if self._active_run_location is None:
            return None
        _, hint = self._classify_launch_failure(RuntimeError("MAPDL launch failed"), self._active_run_location)
        return hint

    def exit(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._mapdl is None:
                return {"connected": False, "closed": False}
            try:
                self._mapdl.exit(force=force)
            finally:
                self._mapdl = None
                self._active_run_location = None
            return {"connected": False, "closed": True}

    def live_smoke(self) -> dict[str, Any]:
        """Solve a fixed two-node axial bar and return its scalar displacement."""
        with self._lock:
            mapdl = self._require_mapdl()
            mapdl.clear()
            mapdl.prep7()
            mapdl.et(1, "LINK180")
            mapdl.mp("EX", 1, 2.0e11)
            mapdl.r(1, 1.0e-3)
            mapdl.n(1, 0.0, 0.0, 0.0)
            mapdl.n(2, 1.0, 0.0, 0.0)
            mapdl.e(1, 2)
            mapdl.d(1, "ALL", 0.0)
            mapdl.d(2, "UY", 0.0)
            mapdl.d(2, "UZ", 0.0)
            mapdl.f(2, "FX", 1000.0)
            mapdl.finish()
            mapdl.slashsolu()
            mapdl.antype("STATIC")
            solver_output = mapdl.solve()
            mapdl.finish()
            mapdl.post1()
            mapdl.set("LAST")
            displacement = float(mapdl.get_value("NODE", 2, "U", "X"))
        expected = 1000.0 * 1.0 / (2.0e11 * 1.0e-3)
        relative_error = abs(displacement - expected) / expected
        if relative_error > 0.02:
            raise RuntimeError(
                f"[SMOKE_RESULT_INVALID] Axial displacement {displacement:g} differs from {expected:g} by more than 2%."
            )
        return {
            "analysis": "fixed_axial_bar",
            "displacement": displacement,
            "expected": expected,
            "relative_error": relative_error,
            "solver_output": str(solver_output)[-2000:],
        }

    def _require_mapdl(self) -> Any:
        if self._mapdl is None:
            raise RuntimeError("MAPDL is not connected. Call launch_mapdl first.")
        return self._mapdl

    def run_apdl(self, commands: str) -> dict[str, Any]:
        if not self.settings.allow_raw_apdl:
            raise PermissionError("Raw APDL is disabled by ANSYS_MCP_ALLOW_RAW_APDL=0")
        if not commands.strip():
            raise ValueError("commands cannot be empty")
        with self._lock:
            output = self._require_mapdl().input_strings(commands)
        return {"output": str(output)}

    def open_database(self, path: str) -> dict[str, Any]:
        database = self.settings.resolve_work_path(path, must_exist=True)
        with self._lock:
            output = self._require_mapdl().resume(str(database))
        return {"database": str(database), "output": str(output)}

    def mesh(self, element_size: float) -> dict[str, Any]:
        if element_size <= 0:
            raise ValueError("element_size must be positive and use the active MAPDL unit system")
        with self._lock:
            mapdl = self._require_mapdl()
            mapdl.prep7()
            mapdl.esize(element_size)
            output = mapdl.vmesh("ALL")
            count = int(getattr(mapdl.mesh, "n_elem", 0))
        return {"element_size": element_size, "element_count": count, "output": str(output)}

    def solve(self, analysis_type: str = "STATIC") -> dict[str, Any]:
        allowed = {"STATIC", "MODAL", "TRANS", "BUCKLE", "HARMIC"}
        analysis_type = analysis_type.upper()
        if analysis_type not in allowed:
            raise ValueError(f"analysis_type must be one of {sorted(allowed)}")
        with self._lock:
            mapdl = self._require_mapdl()
            mapdl.finish()
            mapdl.slashsolu()
            mapdl.antype(analysis_type)
            output = mapdl.solve()
            mapdl.finish()
        self._last_result = {"analysis_type": analysis_type, "solver_output": str(output)}
        return self._last_result

    def _post_values(self, kind: str) -> dict[str, Any]:
        import numpy as np

        if self._last_result and self._last_result["analysis_type"] in {"MODAL", "BUCKLE", "HARMIC"}:
            analysis_type = self._last_result["analysis_type"]
            raise RuntimeError(
                f"Generic scalar {kind} extraction is disabled for {analysis_type}; "
                "use analysis-specific APDL post-processing instead."
            )

        with self._lock:
            mapdl = self._require_mapdl()
            mapdl.post1()
            mapdl.set("LAST")
            result = mapdl.result
            if result.nsets < 1:
                raise RuntimeError("The result file contains no result sets")
            result_index = result.nsets - 1
            if kind == "stress":
                nodes, values = result.principal_nodal_stress(result_index)
                # Equivalent (von Mises) stress is the final column.
                scalar = values[:, -1]
                label = "von_mises"
            else:
                nodes, values = result.nodal_displacement(result_index)
                scalar = (values[:, 0] ** 2 + values[:, 1] ** 2 + values[:, 2] ** 2) ** 0.5
                label = "total_displacement"
            if np.isnan(scalar).all():
                raise RuntimeError(f"The latest result set contains no finite {label} values")
            index = int(np.nanargmax(scalar))
            return {
                "result": label,
                "maximum": float(scalar[index]),
                "node": int(nodes[index]),
                "unit_system": "active MAPDL unit system",
            }

    def get_stress(self) -> dict[str, Any]:
        return self._post_values("stress")

    def get_displacement(self) -> dict[str, Any]:
        return self._post_values("displacement")

    def export_results(self, output_path: str) -> dict[str, Any]:
        target = self.settings.resolve_work_path(output_path)
        if target.suffix.lower() not in {".json", ".csv"}:
            raise ValueError("output_path must end in .json or .csv")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {"stress": self.get_stress(), "displacement": self.get_displacement()}
        if target.suffix.lower() == ".json":
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            with target.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=["result", "maximum", "node", "unit_system"])
                writer.writeheader()
                writer.writerows(data.values())
        return {"path": str(target), "results": data}

    def open_project(self, project_path: str, *, timeout_seconds: int = 1800) -> dict[str, Any]:
        project = self.settings.resolve_work_path(project_path, must_exist=True)
        if project.suffix.lower() != ".wbpj":
            raise ValueError("project_path must be an Ansys Workbench .wbpj file")
        generated = self.settings.work_root / ".ansys-mcp-generated"
        generated.mkdir(parents=True, exist_ok=True)
        journal = generated / f"open-project-{uuid.uuid4().hex}.wbjn"
        escaped = str(project).replace('"""', '\"\"\"')
        journal.write_text(f'Open(FilePath=r"""{escaped}""")\n', encoding="utf-8")
        try:
            return self._run_workbench(["-B", "-R", str(journal)], timeout_seconds)
        finally:
            journal.unlink(missing_ok=True)

    def run_workbench_script(self, script_path: str, *, timeout_seconds: int = 1800) -> dict[str, Any]:
        if not self.settings.allow_workbench_scripts:
            raise PermissionError("Workbench scripts are disabled by ANSYS_MCP_ALLOW_WB_SCRIPTS=0")
        script = self.settings.resolve_work_path(script_path, must_exist=True)
        if script.suffix.lower() not in {".wbjn", ".py"}:
            raise ValueError("script_path must end in .wbjn or .py")
        return self._run_workbench(["-B", "-R", str(script)], timeout_seconds)

    def _run_workbench(self, args: list[str], timeout_seconds: int) -> dict[str, Any]:
        if not self.settings.workbench_exe.is_file():
            raise FileNotFoundError(self.settings.workbench_exe)
        if timeout_seconds < 1 or timeout_seconds > 86400:
            raise ValueError("timeout_seconds must be between 1 and 86400")
        started = datetime.now().isoformat(timespec="seconds")
        process = subprocess.Popen(
            [str(self.settings.workbench_exe), *args],
            cwd=str(self.settings.work_root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            process.wait()
            raise TimeoutError(f"Workbench exceeded {timeout_seconds} seconds; its process tree was terminated") from exc
        ok = process.returncode == 0
        return {
            "started": started,
            "ok": ok,
            "exit_code": process.returncode,
            "stdout": stdout[-12000:],
            "stderr": stderr[-12000:],
        }
