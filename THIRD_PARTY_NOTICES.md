# Third-party notices

This repository contains integration code, not copies of the commercial
solvers or the locked third-party wheels. Dependencies installed by a user keep
their upstream copyright and license terms.

## Gmsh

`fluent-2d-runner` uses the Gmsh 4.13.1 Python API to generate meshes. Gmsh is
distributed under the GNU General Public License, version 2 or later. The wheel
is downloaded separately from PyPI only after explicit user approval and a
pinned SHA-256 check; it is not committed or redistributed here.

- Project and source: <https://gmsh.info/>
- PyPI package: <https://pypi.org/project/gmsh/4.13.1/>

Because the runner imports and calls that API directly, the complete
`fluent-2d-runner` component is offered under GPL-2.0-or-later. Its license text
is in [`fluent-2d-runner/LICENSE`](fluent-2d-runner/LICENSE).

## MCP Python SDK and PyMAPDL

`mcp-server` installs the MCP Python SDK and Ansys PyMAPDL from the versions
declared in its `pyproject.toml` and hash-locked dependency file. Both projects
are distributed under the MIT License at the time of the pinned release. No
dependency source is vendored into this repository.

- MCP Python SDK: <https://github.com/modelcontextprotocol/python-sdk>
- PyMAPDL: <https://github.com/ansys/pymapdl>
- Exact dependency and compatibility record: [`mcp-server/SOURCES.md`](mcp-server/SOURCES.md)

Transitive dependencies have their own licenses. Redistributors of built
packages must review the installed distributions' metadata and notices rather
than treating this file as a complete license inventory.

## Ansys products

Ansys Fluent, Mechanical, MAPDL and Workbench are proprietary products and are
not part of this repository. Users must provide their own valid installation
and license. No Ansys executable, license file, relay configuration, proprietary
example, CAD model, mesh or result file is distributed here.

Ansys, Fluent, Mechanical, MAPDL and Workbench are trademarks of their
respective owner. This project is independent and is not endorsed by Ansys.
