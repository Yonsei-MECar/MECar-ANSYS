# Sources and compatibility basis

Checked on 2026-08-23.

## Locked Python dependencies

- MCP Python SDK `1.29.0`: https://pypi.org/project/mcp/1.29.0/
- PyMAPDL `ansys-mapdl-core` `0.73.2`: https://pypi.org/project/ansys-mapdl-core/0.73.2/
- Hatchling `1.27.0`: https://pypi.org/project/hatchling/1.27.0/
- pytest `8.4.2`: https://pypi.org/project/pytest/8.4.2/

The direct versions above are exact pins in `pyproject.toml`. `requirements.lock.txt` was resolved for Windows x64 from the Python 3.10 minimum compatibility boundary, includes the development/build tools, and records SHA-256 hashes for every resolved distribution. The resolver cutoff is `2026-08-23T00:00:00Z`; changing that cutoff or any pin requires a fresh clean-install, unit, STDIO, and live MAPDL compatibility review.

## Interface and compatibility basis

- PyMAPDL version/interface table: https://mapdl.docs.pyansys.com/version/stable/getting_started/versioning.html
  - Lists Ansys 2021 R1 with the recommended gRPC interface.
- `launch_mapdl` API: https://mapdl.docs.pyansys.com/version/stable/api/_autosummary/ansys.mapdl.core.launcher.launch_mapdl.html
  - Documents `mode="grpc"`, integer `version=211`, processor count, run location, and launch switches.
- PyMAPDL usage/results example: https://mapdl.docs.pyansys.com/version/stable/user_guide/mapdl.html
  - Documents `principal_nodal_stress` and the final equivalent-stress column.
- OpenAI Codex MCP documentation: https://developers.openai.com/codex/mcp/
  - Basis for the project `.codex/config.toml` STDIO server entry.

This project is an independent bridge and is not an Ansys or OpenAI product. Ansys, MAPDL, Mechanical, and Workbench are trademarks of their respective owner.
