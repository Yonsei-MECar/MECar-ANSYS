from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run() -> None:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ansys_mcp_server.server"],
    )
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            expected = {"ansys_status", "launch_mapdl", "run_apdl", "mesh", "solve", "get_stress"}
            missing = expected - names
            if missing:
                raise RuntimeError(f"MCP server is missing tools: {sorted(missing)}")
            result = await session.call_tool("ansys_status", {})
            if result.isError:
                raise RuntimeError(f"ansys_status failed: {result.content}")
            print(f"MCP STDIO handshake passed ({len(names)} tools; ansys_status succeeded).")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

