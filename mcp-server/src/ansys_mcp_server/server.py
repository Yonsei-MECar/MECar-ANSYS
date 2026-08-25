from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .backend import AnsysBackend
from .config import Settings

settings = Settings.from_env()
backend = AnsysBackend(settings)
mcp = FastMCP(
    "MECar Ansys 2021 R1",
    instructions=(
        "Use ansys_status first and launch_mapdl before MAPDL tools. "
        "Never infer units: all numeric values use the model's active consistent unit system. "
        "Raw APDL and Workbench scripts can execute commands and access files outside the work root; "
        "use them only when the user has authorized that code. Generic maximum results support static "
        "and transient analyses; use analysis-specific APDL post-processing for modal, buckling, or harmonic results."
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False)
CODE_EXEC = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)


@mcp.tool(annotations=READ_ONLY)
def ansys_status() -> dict:
    """Check Ansys installation paths, policy flags, and MAPDL connection state."""
    return backend.status()


@mcp.tool(annotations=MUTATING)
def launch_mapdl(nproc: int = 2, additional_switches: str = "") -> dict:
    """Launch and connect to local MAPDL 2021 R1 over gRPC."""
    return backend.launch(nproc=nproc, additional_switches=additional_switches)


@mcp.tool(annotations=DESTRUCTIVE)
def close_mapdl(force: bool = False) -> dict:
    """Close the MAPDL process owned by this MCP server."""
    return backend.exit(force=force)


@mcp.tool(annotations=CODE_EXEC)
def run_apdl(commands: str) -> dict:
    """Run raw APDL commands in the connected MAPDL session. This can modify the model."""
    return backend.run_apdl(commands)


@mcp.tool(annotations=DESTRUCTIVE)
def open_database(path: str) -> dict:
    """Resume a MAPDL database located inside ANSYS_MCP_WORK_ROOT."""
    return backend.open_database(path)


@mcp.tool(annotations=DESTRUCTIVE)
def mesh(element_size: float) -> dict:
    """Mesh all currently selected volumes with a positive global element size."""
    return backend.mesh(element_size)


@mcp.tool(annotations=DESTRUCTIVE)
def solve(analysis_type: str = "STATIC") -> dict:
    """Solve the current MAPDL database using STATIC, MODAL, TRANS, BUCKLE, or HARMIC."""
    return backend.solve(analysis_type)


@mcp.tool(annotations=READ_ONLY)
def get_stress() -> dict:
    """Return maximum nodal von Mises stress from the latest MAPDL result set."""
    return backend.get_stress()


@mcp.tool(annotations=READ_ONLY)
def get_displacement() -> dict:
    """Return maximum total nodal displacement from the latest MAPDL result set."""
    return backend.get_displacement()


@mcp.tool(annotations=DESTRUCTIVE)
def export_results(output_path: str) -> dict:
    """Export stress and displacement summaries to JSON or CSV inside the work root."""
    return backend.export_results(output_path)


@mcp.tool(annotations=MUTATING)
def open_project(project_path: str, timeout_seconds: int = 1800) -> dict:
    """Load a Workbench .wbpj project in batch mode. The project must be inside the work root."""
    return backend.open_project(project_path, timeout_seconds=timeout_seconds)


@mcp.tool(annotations=CODE_EXEC)
def run_workbench_script(script_path: str, timeout_seconds: int = 1800) -> dict:
    """Run an existing Workbench journal/script inside the work root with RunWB2 -B -R."""
    return backend.run_workbench_script(script_path, timeout_seconds=timeout_seconds)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
