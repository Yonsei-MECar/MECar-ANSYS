from __future__ import annotations

import csv
import math
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .errors import EnvironmentError, InputError
from .manifest import resolve_airfoil_path
from .util import atomic_write_json, sha256_file


def naca4_points(identifier: str, count_per_surface: int = 121) -> list[tuple[float, float]]:
    """Return a closed clockwise TE-upper-LE-lower-TE NACA four-digit profile."""
    digits = identifier.upper().removeprefix("NACA")
    if len(digits) != 4 or not digits.isdigit():
        raise InputError(f"invalid NACA four-digit identifier: {identifier}")
    m = int(digits[0]) / 100.0
    p = int(digits[1]) / 10.0
    thickness = int(digits[2:]) / 100.0
    beta = [math.pi * i / (count_per_surface - 1) for i in range(count_per_surface)]
    x_values = [(1.0 - math.cos(value)) / 2.0 for value in beta]

    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    for x in x_values:
        yt = 5.0 * thickness * (
            0.2969 * math.sqrt(max(x, 0.0))
            - 0.1260 * x
            - 0.3516 * x**2
            + 0.2843 * x**3
            - 0.1015 * x**4
        )
        if m == 0.0 or p == 0.0:
            yc = 0.0
            dyc = 0.0
        elif x < p:
            yc = m / p**2 * (2.0 * p * x - x**2)
            dyc = 2.0 * m / p**2 * (p - x)
        else:
            yc = m / (1.0 - p) ** 2 * ((1.0 - 2.0 * p) + 2.0 * p * x - x**2)
            dyc = 2.0 * m / (1.0 - p) ** 2 * (p - x)
        theta = math.atan(dyc)
        upper.append((x - yt * math.sin(theta), yc + yt * math.cos(theta)))
        lower.append((x + yt * math.sin(theta), yc - yt * math.cos(theta)))

    # The -0.1015 coefficient leaves a tiny finite trailing-edge thickness. The
    # geometry closes it with a distinct straight segment, avoiding coincident points.
    return list(reversed(upper)) + lower[1:]


def read_selig_dat(path: Path) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
        for number, line in enumerate(stream, start=1):
            stripped = line.strip().replace(",", " ")
            if not stripped or stripped.startswith(("#", ";")):
                continue
            parts = stripped.split()
            if len(parts) < 2:
                continue
            try:
                x, y = float(parts[0]), float(parts[1])
            except ValueError:
                if not points:
                    continue
                raise InputError(f"invalid airfoil coordinate at {path.name}:{number}")
            if not math.isfinite(x) or not math.isfinite(y):
                raise InputError(f"non-finite airfoil coordinate at {path.name}:{number}")
            points.append((x, y))
    if len(points) < 20:
        raise InputError(f"airfoil DAT has fewer than 20 usable points: {path.name}")
    x_min = min(x for x, _ in points)
    x_max = max(x for x, _ in points)
    if x_max - x_min <= 0:
        raise InputError(f"airfoil DAT has no positive chord extent: {path.name}")
    normalized = [((x - x_min) / (x_max - x_min), y / (x_max - x_min)) for x, y in points]
    if _signed_polygon_area(normalized) > 0:
        normalized.reverse()
    return normalized


def _signed_polygon_area(points: Iterable[tuple[float, float]]) -> float:
    values = list(points)
    return 0.5 * sum(
        values[index][0] * values[(index + 1) % len(values)][1]
        - values[(index + 1) % len(values)][0] * values[index][1]
        for index in range(len(values))
    )


def transformed_points(data: dict[str, Any], manifest_root: Path) -> list[tuple[float, float]]:
    mesh = data["mesh"]
    airfoil = mesh["airfoil"]
    if airfoil["sourceType"] == "procedural-naca4":
        base = naca4_points(airfoil["id"])
    else:
        path = resolve_airfoil_path(data, manifest_root)
        assert path is not None
        base = read_selig_dat(path)
    chord = float(mesh["chordM"])
    alpha = math.radians(float(mesh["angleDeg"]))
    pivot = 0.25
    cosine, sine = math.cos(alpha), math.sin(alpha)
    rotated = []
    for x, y in base:
        x0, y0 = x - pivot, y
        rotated.append(((x0 * cosine - y0 * sine + pivot) * chord, (x0 * sine + y0 * cosine) * chord))
    y_shift = float(mesh["heightM"]) - min(y for _, y in rotated)
    return [(x, y + y_shift) for x, y in rotated]


def _triangle_quality(nodes: dict[int, tuple[float, float]], cell: tuple[int, ...]) -> tuple[float, float]:
    coordinates = [nodes[tag] for tag in cell]
    area = abs(_signed_polygon_area(coordinates))
    lengths = []
    for index in range(len(coordinates)):
        x0, y0 = coordinates[index]
        x1, y1 = coordinates[(index + 1) % len(coordinates)]
        lengths.append(math.hypot(x1 - x0, y1 - y0))
    if area <= 0 or min(lengths) <= 0:
        return area, 0.0
    quality = 4.0 * math.sqrt(3.0) * area / sum(length**2 for length in lengths)
    return area, quality


def _extract_gmsh(gmsh: Any) -> tuple[dict[int, tuple[float, float]], list[tuple[int, ...]], dict[str, set[frozenset[int]]]]:
    node_tags, coordinates, _ = gmsh.model.mesh.getNodes()
    nodes = {
        int(tag): (float(coordinates[3 * index]), float(coordinates[3 * index + 1]))
        for index, tag in enumerate(node_tags)
    }
    cells: list[tuple[int, ...]] = []
    element_types, element_tags, element_nodes = gmsh.model.mesh.getElements(2)
    for element_type, tags, flat_nodes in zip(element_types, element_tags, element_nodes):
        width = {2: 3, 3: 4}.get(int(element_type))
        if width is None:
            continue
        values = [int(value) for value in flat_nodes]
        for index in range(len(tags)):
            cell = tuple(values[width * index : width * (index + 1)])
            coordinates_for_cell = [nodes[tag] for tag in cell]
            if _signed_polygon_area(coordinates_for_cell) < 0:
                cell = tuple(reversed(cell))
            cells.append(cell)
    boundaries: dict[str, set[frozenset[int]]] = {}
    for dimension, physical_tag in gmsh.model.getPhysicalGroups(1):
        name = gmsh.model.getPhysicalName(dimension, physical_tag)
        edges: set[frozenset[int]] = set()
        for entity in gmsh.model.getEntitiesForPhysicalGroup(dimension, physical_tag):
            types, tags_by_type, nodes_by_type = gmsh.model.mesh.getElements(1, entity)
            for element_type, tags, flat_nodes in zip(types, tags_by_type, nodes_by_type):
                if int(element_type) != 1:
                    continue
                values = [int(value) for value in flat_nodes]
                for index in range(len(tags)):
                    edges.add(frozenset((values[2 * index], values[2 * index + 1])))
        boundaries[name] = edges
    return nodes, cells, boundaries


def write_fluent_ascii(
    path: Path,
    nodes: dict[int, tuple[float, float]],
    cells: list[tuple[int, ...]],
    boundaries: dict[str, set[frozenset[int]]],
) -> dict[str, Any]:
    """Write a legacy Fluent ASCII 2D mesh accepted by Fluent 2021 R1."""
    if not cells:
        raise InputError("Gmsh produced no supported 2D cells")
    node_map = {tag: index for index, tag in enumerate(sorted(nodes), start=1)}
    face_owners: dict[frozenset[int], list[tuple[int, int, int]]] = defaultdict(list)
    for cell_id, cell in enumerate(cells, start=1):
        for index, first in enumerate(cell):
            second = cell[(index + 1) % len(cell)]
            face_owners[frozenset((first, second))].append((first, second, cell_id))

    edge_zone: dict[frozenset[int], str] = {}
    for name, edges in boundaries.items():
        for edge in edges:
            if edge in edge_zone:
                raise InputError(f"mesh edge belongs to multiple boundary zones: {name}, {edge_zone[edge]}")
            edge_zone[edge] = name

    interior: list[tuple[int, int, int, int]] = []
    zone_faces: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    for edge, owners in face_owners.items():
        if len(owners) == 2:
            first, second = owners
            a, b, left_cell = first
            if (second[0], second[1]) != (b, a):
                raise InputError("adjacent cells have inconsistent orientation")
            right_cell = second[2]
            # Fluent's 2D ASCII face tuple stores the owner on the geometric
            # left of n0->n1 first. Keeping CCW cell edges therefore yields
            # positive volumes in v211.
            interior.append((a, b, left_cell, right_cell))
        elif len(owners) == 1:
            a, b, left_cell = owners[0]
            zone_name = edge_zone.get(edge)
            if zone_name is None:
                raise InputError("mesh contains an unassigned exterior face")
            zone_faces[zone_name].append((a, b, left_cell, 0))
        else:
            raise InputError(f"non-manifold mesh face has {len(owners)} owners")

    required_zones = {"inlet", "outlet", "top", "ground", "wing"}
    if set(zone_faces) != required_zones:
        raise InputError(f"boundary zones mismatch: expected {sorted(required_zones)}, got {sorted(zone_faces)}")

    cell_zone_id = 2
    interior_zone_id = 3
    zone_ids = {name: index for index, name in enumerate(sorted(zone_faces), start=4)}
    face_count = len(interior) + sum(len(values) for values in zone_faces.values())
    hex_value = lambda value: format(value, "x")
    lines = ['(0 "MECar gmsh-4.13.1 to Fluent 2021 R1 2D")', "(2 2)"]
    lines.append(f"(10 (0 1 {hex_value(len(nodes))} 0 2))")
    lines.append(f"(10 (1 1 {hex_value(len(nodes))} 1 2)(")
    for tag in sorted(nodes):
        x, y = nodes[tag]
        lines.append(f"{x:.16e} {y:.16e}")
    lines.append("))")
    lines.append(f"(12 (0 1 {hex_value(len(cells))} 0))")
    cell_types = {len(cell) for cell in cells}
    if cell_types == {3}:
        lines.append(f"(12 ({hex_value(cell_zone_id)} 1 {hex_value(len(cells))} 1 1))")
    elif cell_types == {4}:
        lines.append(f"(12 ({hex_value(cell_zone_id)} 1 {hex_value(len(cells))} 1 3))")
    else:
        lines.append(f"(12 ({hex_value(cell_zone_id)} 1 {hex_value(len(cells))} 1 0)(")
        lines.extend("1" if len(cell) == 3 else "3" for cell in cells)
        lines.append("))")
    lines.append(f"(13 (0 1 {hex_value(face_count)} 0))")
    next_face = 1
    last_face = len(interior)
    lines.append(f"(13 ({hex_value(interior_zone_id)} {hex_value(next_face)} {hex_value(last_face)} 2 2)(")
    for a, b, c0, c1 in interior:
        lines.append(f"{hex_value(node_map[a])} {hex_value(node_map[b])} {hex_value(c0)} {hex_value(c1)}")
    lines.append("))")
    next_face = last_face + 1
    boundary_codes = {"inlet": 10, "outlet": 5, "top": 7, "ground": 3, "wing": 3}
    for name in sorted(zone_faces):
        values = zone_faces[name]
        last_face = next_face + len(values) - 1
        lines.append(
            f"(13 ({hex_value(zone_ids[name])} {hex_value(next_face)} {hex_value(last_face)} "
            f"{hex_value(boundary_codes[name])} 2)("
        )
        for a, b, c0, c1 in values:
            lines.append(f"{hex_value(node_map[a])} {hex_value(node_map[b])} {hex_value(c0)} {hex_value(c1)}")
        lines.append("))")
        next_face = last_face + 1
    lines.append(f"(45 ({cell_zone_id} fluid fluid)())")
    lines.append(f"(45 ({interior_zone_id} interior interior-fluid)())")
    zone_types = {"inlet": "velocity-inlet", "outlet": "pressure-outlet", "top": "symmetry", "ground": "wall", "wing": "wall"}
    for name in sorted(zone_faces):
        lines.append(f"(45 ({zone_ids[name]} {zone_types[name]} {name})())")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")
    return {
        "nodeCount": len(nodes),
        "cellCount": len(cells),
        "faceCount": face_count,
        "interiorFaceCount": len(interior),
        "boundaryFaceCounts": {name: len(values) for name, values in sorted(zone_faces.items())},
    }


def build_mesh(data: dict[str, Any], manifest_root: Path, case_dir: Path) -> dict[str, Any]:
    try:
        import gmsh  # type: ignore
    except (ImportError, OSError) as exc:
        raise EnvironmentError(
            "gmsh 4.13.1 is not importable",
            hint="Run scripts/setup_gmsh.ps1; it verifies the pinned wheel before installation.",
        ) from exc
    if getattr(gmsh, "__version__", None) != "4.13.1":
        raise EnvironmentError(f"gmsh version must be 4.13.1, found {getattr(gmsh, '__version__', 'unknown')}")

    points = transformed_points(data, manifest_root)
    source_path = resolve_airfoil_path(data, manifest_root)
    if source_path is not None:
        copied_source = case_dir / "input" / "airfoil.dat"
        copied_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, copied_source)
    mesh = data["mesh"]
    chord = float(mesh["chordM"])
    x_min = -float(mesh["domainUpstreamChord"]) * chord
    x_max = float(mesh["domainDownstreamChord"]) * chord
    y_max = float(mesh["domainTopChord"]) * chord
    surface_size = float(mesh["sizing"]["surfaceSizeM"])
    farfield_size = float(mesh["sizing"]["farfieldSizeM"])
    boundary_layer = mesh["sizing"]["boundaryLayer"]
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setNumber("Mesh.MaxNumThreads1D", 1)
        gmsh.option.setNumber("Mesh.MaxNumThreads2D", 1)
        gmsh.option.setNumber("Mesh.MaxNumThreads3D", 1)
        gmsh.option.setNumber("Mesh.RandomSeed", 1)
        gmsh.option.setNumber("Mesh.RandomFactor", 0)
        gmsh.model.add(data["caseId"])
        geometry = gmsh.model.geo
        profile_tags = [geometry.addPoint(x, y, 0.0, surface_size) for x, y in points]
        profile_lines = [
            geometry.addLine(profile_tags[index], profile_tags[(index + 1) % len(profile_tags)])
            for index in range(len(profile_tags))
        ]
        profile_loop = geometry.addCurveLoop(profile_lines)
        domain_tags = [
            geometry.addPoint(x_min, 0.0, 0.0, farfield_size),
            geometry.addPoint(x_max, 0.0, 0.0, farfield_size),
            geometry.addPoint(x_max, y_max, 0.0, farfield_size),
            geometry.addPoint(x_min, y_max, 0.0, farfield_size),
        ]
        ground = geometry.addLine(domain_tags[0], domain_tags[1])
        outlet = geometry.addLine(domain_tags[1], domain_tags[2])
        top = geometry.addLine(domain_tags[2], domain_tags[3])
        inlet = geometry.addLine(domain_tags[3], domain_tags[0])
        domain_loop = geometry.addCurveLoop([ground, outlet, top, inlet])
        surface = geometry.addPlaneSurface([domain_loop, profile_loop])
        geometry.synchronize()
        groups = {
            "inlet": [inlet],
            "outlet": [outlet],
            "top": [top],
            "ground": [ground],
            "wing": profile_lines,
        }
        for name, entities in groups.items():
            tag = gmsh.model.addPhysicalGroup(1, entities)
            gmsh.model.setPhysicalName(1, tag, name)
        fluid_tag = gmsh.model.addPhysicalGroup(2, [surface])
        gmsh.model.setPhysicalName(2, fluid_tag, "fluid")
        field = gmsh.model.mesh.field
        field.add("Distance", 1)
        field.setNumbers(1, "CurvesList", profile_lines)
        field.setNumber(1, "Sampling", 400)
        field.add("Threshold", 2)
        field.setNumber(2, "InField", 1)
        field.setNumber(2, "SizeMin", surface_size)
        field.setNumber(2, "SizeMax", farfield_size)
        field.setNumber(2, "DistMin", 0.1 * chord)
        field.setNumber(2, "DistMax", 2.0 * chord)
        field.setAsBackgroundMesh(2)
        if boundary_layer["enabled"]:
            first_layer = float(boundary_layer["firstLayerM"])
            growth = float(boundary_layer["growthRatio"])
            layer_count = int(boundary_layer["layerCount"])
            total_thickness = first_layer * (growth**layer_count - 1.0) / (growth - 1.0)
            field.add("BoundaryLayer", 10)
            field.setNumbers(10, "CurvesList", profile_lines)
            field.setNumber(10, "Size", first_layer)
            field.setNumber(10, "Ratio", growth)
            field.setNumber(10, "Thickness", total_thickness)
            field.setNumber(10, "Quads", 1)
            field.setAsBoundaryLayer(10)
        gmsh.option.setNumber("Mesh.Algorithm", 5)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 1)
        gmsh.model.mesh.generate(2)
        nodes, cells, boundaries = _extract_gmsh(gmsh)
        areas_and_quality = [_triangle_quality(nodes, cell) for cell in cells]
        min_area = min(value[0] for value in areas_and_quality)
        min_quality = min(value[1] for value in areas_and_quality)
        if min_area <= 0 or min_quality <= 0:
            raise InputError("mesh quality is invalid (non-positive cell or zero quality)")
        output_mesh = case_dir / "input" / "mesh.msh"
        topology = write_fluent_ascii(output_mesh, nodes, cells, boundaries)
        quality = {
            **topology,
            "gmshVersion": gmsh.__version__,
            "generatorVersion": mesh["generatorVersion"],
            "fluentMeshSha256": sha256_file(output_mesh),
            "boundaryLayer": {
                "enabled": bool(boundary_layer["enabled"]),
                "firstLayerM": float(boundary_layer["firstLayerM"]),
                "growthRatio": float(boundary_layer["growthRatio"]),
                "layerCount": int(boundary_layer["layerCount"]),
            },
            "minimumCellAreaM2": min_area,
            "minimumNormalizedTriangleQuality": min_quality,
            "gate": {"positiveArea": min_area > 0.0, "minimumQualityAbove0_01": min_quality >= 0.01},
            "passed": min_area > 0.0 and min_quality >= 0.01,
        }
        reports = case_dir / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        atomic_write_json(reports / "mesh-quality.json", quality)
        with (reports / "mesh-cells.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["cell", "area_m2", "normalized_quality"])
            for index, (area, quality_value) in enumerate(areas_and_quality, start=1):
                writer.writerow([index, f"{area:.16g}", f"{quality_value:.16g}"])
        if not quality["passed"]:
            raise InputError(
                "mesh quality gate failed before Fluent launch "
                f"(minimum area={min_area:.6g} m^2, minimum quality={min_quality:.6g}, required quality>=0.01)"
            )
        return quality
    finally:
        gmsh.finalize()
