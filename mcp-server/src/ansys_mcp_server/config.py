from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    ansys_version: int
    ansys_root: Path
    work_root: Path
    run_location: Path
    workbench_exe: Path
    mapdl_exe: Path
    allow_raw_apdl: bool
    allow_workbench_scripts: bool

    @classmethod
    def from_env(cls) -> "Settings":
        ansys_root = _env_path("ANSYS_MCP_ANSYS_ROOT", Path(r"C:\Program Files\ANSYS Inc\v211"))
        work_root = _env_path("ANSYS_MCP_WORK_ROOT", Path.cwd())
        run_location = _env_path("ANSYS_MCP_RUN_LOCATION", work_root / ".ansys-mcp-runs")
        workbench = _env_path(
            "ANSYS_MCP_WORKBENCH_EXE",
            ansys_root / "Framework" / "bin" / "Win64" / "RunWB2.exe",
        )
        mapdl = _env_path(
            "ANSYS_MCP_MAPDL_EXE",
            ansys_root / "ansys" / "bin" / "winx64" / "ANSYS211.exe",
        )
        return cls(
            ansys_version=int(os.environ.get("ANSYS_MCP_VERSION", "211")),
            ansys_root=ansys_root,
            work_root=work_root,
            run_location=run_location,
            workbench_exe=workbench,
            mapdl_exe=mapdl,
            allow_raw_apdl=os.environ.get("ANSYS_MCP_ALLOW_RAW_APDL", "0") == "1",
            allow_workbench_scripts=os.environ.get("ANSYS_MCP_ALLOW_WB_SCRIPTS", "0") == "1",
        )

    def resolve_work_path(self, value: str, *, must_exist: bool = False) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = self.work_root / candidate
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.work_root)
        except ValueError as exc:
            raise ValueError(f"Path must stay inside ANSYS_MCP_WORK_ROOT: {self.work_root}") from exc
        if must_exist and not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate
