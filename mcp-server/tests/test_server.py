import asyncio

from ansys_mcp_server.server import mcp


def test_expected_mcp_tools_are_registered():
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert names == {
        "ansys_status",
        "launch_mapdl",
        "close_mapdl",
        "run_apdl",
        "open_database",
        "mesh",
        "solve",
        "get_stress",
        "get_displacement",
        "export_results",
        "open_project",
        "run_workbench_script",
    }
    by_name = {tool.name: tool for tool in tools}
    assert by_name["ansys_status"].annotations.readOnlyHint is True
    assert by_name["run_apdl"].annotations.destructiveHint is True
    assert by_name["run_apdl"].annotations.openWorldHint is True
