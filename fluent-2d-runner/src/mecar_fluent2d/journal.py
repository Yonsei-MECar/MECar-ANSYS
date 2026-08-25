from __future__ import annotations

from pathlib import Path
from typing import Any

from .util import posix_for_fluent


def _quote(path: Path) -> str:
    return f'"{posix_for_fluent(path)}"'


def build_mesh_probe_journal(case_dir: Path) -> str:
    """Small v211 journal used to verify the generated mesh without solving."""
    mesh = case_dir / "input" / "mesh.msh"
    transcript = case_dir / "logs" / "mesh-probe.trn"
    output_case = case_dir / "artifacts" / "mesh-probe.cas.h5"
    return "\n".join(
        [
            '; MECar Fluent 2021 R1 mesh compatibility probe',
            '/file/set-tui-version "21.1"',
            f"/file/start-transcript {_quote(transcript)}",
            # Fluent 2021 R1 reads a native .msh through read-case; the newer
            # read-mesh TUI leaf is not present in this release.
            f"/file/read-case {_quote(mesh)}",
            "/mesh/check",
            f"/file/write-case {_quote(output_case)}",
            "/file/stop-transcript",
            "/exit yes",
            "",
        ]
    )


def build_journal(data: dict[str, Any], case_dir: Path) -> str:
    """Build a template-free native TUI 21.1 journal.

    The case is configured from the generated mesh every run. No .cas template is
    read, so a newer Fluent file can never be consumed accidentally.
    """
    mesh_path = case_dir / "input" / "mesh.msh"
    transcript = case_dir / "logs" / "fluent.trn"
    artifacts = case_dir / "artifacts"
    reports = case_dir / "reports"
    flow = data["flow"]
    reference = data["reference"]
    iterations = data["iterations"]
    warmup = int(iterations["warmup"])
    second_order = int(iterations["secondOrder"])
    sample_every = int(iterations["sampleEvery"])

    lines = [
        "; MECar Fluent 2021 R1 2D journal - generated, do not hand edit",
        "; No prebuilt or newer-version case dependency is permitted.",
        '/file/set-tui-version "21.1"',
        f"/file/start-transcript {_quote(transcript)}",
        f"/file/read-case {_quote(mesh_path)}",
        "/mesh/check",
        "; MECAR_SETUP_BEGIN",
        "/define/models/viscous/kw-sst yes",
        # Material change-create prompt sequence for constant density and viscosity.
        # Kept on separate lines so the v211 transcript identifies any prompt drift.
        "/define/materials/change-create air air",
        "yes", "constant", f'{float(flow["densityKgM3"]):.16g}',
        "no", "no",
        "yes", "constant", f'{float(flow["viscosityPaS"]):.16g}',
        "no", "no", "no",
        # v211 velocity-inlet prompt sequence: frame, velocity specification,
        # components, temperature, turbulence specification/intensity/ratio.
        "/define/boundary-conditions/velocity-inlet inlet",
        "no", "no", "yes", "yes", "no", f'{float(flow["velocityMps"]):.16g}',
        "no", "0",
        "no", "no", "yes",
        f'{100.0 * float(flow["turbulenceIntensity"]):.16g}',
        f'{float(flow["turbulentViscosityRatio"]):.16g}',
        "/define/boundary-conditions/wall ground",
        "yes", "motion-bc-moving",
        "no", "no", "yes", "no", "no",
        f'{float(flow["velocityMps"]):.16g}', "1", "0", "no",
        "no", "0", "no", "0.5",
        "; MECAR_SETUP_END",
        f'/report/reference-values/density {float(flow["densityKgM3"]):.16g}',
        f'/report/reference-values/velocity {float(flow["velocityMps"]):.16g}',
        f'/report/reference-values/area {float(reference["areaM2"]):.16g}',
        f'/report/reference-values/length {float(reference["lengthM"]):.16g}',
        # Fixed iteration batches are evaluated by our stricter engineering
        # gate; Fluent's looser default convergence criterion must not stop a
        # requested chunk after a single iteration.
        "/solve/monitors/residual/check-convergence? no",
        "no", "no", "no", "no",
        "/solve/set/discretization-scheme/mom 0",
        "/solve/set/discretization-scheme/k 0",
        "/solve/set/discretization-scheme/omega 0",
        "/solve/initialize/hyb-initialization",
        f"/solve/iterate {warmup}",
        "/solve/set/discretization-scheme/mom 1",
        "/solve/set/discretization-scheme/k 1",
        "/solve/set/discretization-scheme/omega 1",
    ]
    completed = 0
    while completed < second_order:
        chunk = min(sample_every, second_order - completed)
        completed += chunk
        total_iteration = warmup + completed
        lines.extend(
            [
                f"; MECAR_FORCE_SAMPLE iteration={total_iteration}",
                f"/solve/iterate {chunk}",
                "/report/forces/wall-forces",
                "no", "wing", "", "1", "0", "no",
            ]
        )
    lines.extend(
        [
            "; MECAR_FINAL_FORCE",
            "/report/forces/wall-forces",
            "no", "wing", "", "1", "0", "no",
            "; MECAR_MASS_FLOW",
            "/report/fluxes/mass-flow",
            "no", "inlet", "outlet", "", "no",
            f"/file/write-case-data {_quote(artifacts / 'case.cas.h5')}",
            # Create graphics objects from solved fields. The runner uses -gu
            # (GUI disabled, graphics enabled); -g would make these unavailable.
            "/display/objects/create", "contour", "velocity-contour",
            "field", "velocity-magnitude",
            "filled?", "yes", "contour-lines?", "no",
            "q",
            "/display/objects/create", "contour", "pressure-contour",
            "field", "pressure",
            "filled?", "yes", "contour-lines?", "no",
            "q",
            "/display/objects/create", "vector", "velocity-vector",
            "q",
            "/display/set/picture/driver/png",
            "/display/set/picture/use-window-resolution? no",
            "/display/set/picture/x-resolution 1600",
            "/display/set/picture/y-resolution 900",
            "/display/objects/display velocity-contour",
            f"/display/save-picture {_quote(artifacts / 'velocity-contour.png')}",
            "/display/objects/display pressure-contour",
            f"/display/save-picture {_quote(artifacts / 'pressure-contour.png')}",
            "/display/objects/display velocity-vector",
            f"/display/save-picture {_quote(artifacts / 'vector.png')}",
            "; MECAR_RUN_COMPLETE",
            "/file/stop-transcript",
            "/exit yes",
            "",
        ]
    )
    return "\n".join(lines)


def build_extension_journal(
    data: dict[str, Any],
    case_dir: Path,
    *,
    extension_index: int,
    start_iteration: int,
    count: int,
) -> str:
    """Continue a completed case in bounded chunks up to the declared hard maximum."""
    artifacts = case_dir / "artifacts"
    transcript = case_dir / "logs" / f"fluent-extension-{extension_index:03d}.trn"
    sample_every = int(data["iterations"]["sampleEvery"])
    lines = [
        "; MECar Fluent 2021 R1 bounded convergence extension",
        '/file/set-tui-version "21.1"',
        f"/file/start-transcript {_quote(transcript)}",
        f"/file/read-case-data {_quote(artifacts / 'case.cas.h5')}",
        "/solve/monitors/residual/check-convergence? no",
        "no", "no", "no", "no",
    ]
    completed = 0
    while completed < count:
        chunk = min(sample_every, count - completed)
        completed += chunk
        iteration = start_iteration + completed
        lines.extend(
            [
                f"; MECAR_FORCE_SAMPLE iteration={iteration}",
                f"/solve/iterate {chunk}",
                "/report/forces/wall-forces", "no", "wing", "", "1", "0", "no",
            ]
        )
    lines.extend(
        [
            "; MECAR_FINAL_FORCE",
            "/report/forces/wall-forces", "no", "wing", "", "1", "0", "no",
            "; MECAR_MASS_FLOW",
            "/report/fluxes/mass-flow", "no", "inlet", "outlet", "", "no",
            f"/file/write-case-data {_quote(artifacts / 'case.cas.h5')}", "ok",
            "/display/objects/create", "contour", "velocity-contour",
            "field", "velocity-magnitude", "filled?", "yes", "contour-lines?", "no",
            "q",
            "/display/objects/create", "contour", "pressure-contour",
            "field", "pressure", "filled?", "yes", "contour-lines?", "no",
            "q",
            "/display/objects/create", "vector", "velocity-vector",
            "q",
            "/display/set/picture/driver/png",
            "/display/set/picture/use-window-resolution? no",
            "/display/set/picture/x-resolution 1600",
            "/display/set/picture/y-resolution 900",
            "/display/objects/display velocity-contour",
            f"/display/save-picture {_quote(artifacts / 'velocity-contour.png')}",
            "/display/objects/display pressure-contour",
            f"/display/save-picture {_quote(artifacts / 'pressure-contour.png')}",
            "/display/objects/display velocity-vector",
            f"/display/save-picture {_quote(artifacts / 'vector.png')}",
            "; MECAR_RUN_COMPLETE",
            "/file/stop-transcript",
            "/exit yes",
            "",
        ]
    )
    return "\n".join(lines)
