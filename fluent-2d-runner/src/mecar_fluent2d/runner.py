from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

from .errors import EnvironmentError, Fluent2DError, SolverError
from .gates import evaluate_engineering_gates
from .journal import build_extension_journal, build_journal
from .manifest import load_manifest, manifest_hash
from .mesh import build_mesh
from .parser import FATAL_PATTERNS, parse_transcripts, write_monitor_csvs
from .util import atomic_write_json, resolve_under, sha256_file


ARTIFACT_LOCATIONS = {
    "report.json": ("reports", "report.json"),
    "summary.html": ("reports", "summary.html"),
    "residuals.csv": ("reports", "residuals.csv"),
    "forces.csv": ("reports", "forces.csv"),
    "mesh-quality.json": ("reports", "mesh-quality.json"),
    "vector.png": ("artifacts", "vector.png"),
    "velocity-contour.png": ("artifacts", "velocity-contour.png"),
    "pressure-contour.png": ("artifacts", "pressure-contour.png"),
    "case.cas.h5": ("artifacts", "case.cas.h5"),
    "case.dat.h5": ("artifacts", "case.dat.h5"),
}


def discover_fluent(executable: str | Path | None = None) -> Path:
    candidates: list[Path] = []
    if executable:
        candidates.append(Path(executable))
    awp_root = os.environ.get("AWP_ROOT211")
    if awp_root:
        candidates.append(Path(awp_root) / "fluent" / "ntbin" / "win64" / "fluent.exe")
    candidates.append(Path(r"C:\Program Files\ANSYS Inc\v211\fluent\ntbin\win64\fluent.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise EnvironmentError(
        "Fluent 2021 R1 executable was not found",
        hint="Pass --fluent-exe or configure AWP_ROOT211. Newer Fluent releases are intentionally rejected.",
    )


def _case_path(case_dir: Path, name: str) -> Path:
    first, second = ARTIFACT_LOCATIONS[name]
    return case_dir / first / second


def _present_artifacts(case_dir: Path, *, include_generated_report: bool = False) -> set[str]:
    present = set()
    for name in ARTIFACT_LOCATIONS:
        path = _case_path(case_dir, name)
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        if name.endswith(".png") and path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            continue
        present.add(name)
    if include_generated_report:
        present.update({"report.json", "summary.html"})
    return present


def _verified_resume(case_dir: Path, data: dict[str, Any], result: dict[str, Any]) -> bool:
    if (
        result.get("manifestHash") != manifest_hash(data)
        or not result.get("process", {}).get("passed")
        or not result.get("engineering", {}).get("passed")
    ):
        return False
    checksums = result.get("artifactChecksums")
    if not isinstance(checksums, dict):
        return False
    for name in data["artifacts"]["required"]:
        path = _case_path(case_dir, name)
        if name not in _present_artifacts(case_dir):
            return False
        # A report cannot contain a stable checksum of itself. Its integrity is
        # covered by manifestHash plus the checksums of every other artifact.
        if name != "report.json" and checksums.get(name) != sha256_file(path):
            return False
    return True


def _acquire_lock(case_dir: Path) -> tuple[int, Path]:
    case_dir.mkdir(parents=True, exist_ok=True)
    lock = case_dir / "case.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SolverError(f"case is already locked: {case_dir.name}") from exc
    os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
    return descriptor, lock


def _release_lock(descriptor: int, lock: Path) -> None:
    os.close(descriptor)
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def _clean_run_outputs(case_dir: Path) -> None:
    for name in ("vector.png", "velocity-contour.png", "pressure-contour.png", "case.cas.h5", "case.dat.h5"):
        path = case_dir / "artifacts" / name
        if path.is_file():
            path.unlink()
    for path in (case_dir / "logs").glob("fluent*.trn"):
        if path.is_file():
            path.unlink()
    for path in (case_dir / "logs").glob("console-*.log"):
        if path.is_file():
            path.unlink()
    for name in ("report.json", "summary.html", "residuals.csv", "forces.csv", "mesh-quality.json", "mesh-cells.csv"):
        path = case_dir / "reports" / name
        if path.is_file():
            path.unlink()
    status = case_dir / "status.json"
    if status.is_file():
        status.unlink()
    for path in (case_dir / "journal").glob("extension-*.jou"):
        if path.is_file():
            path.unlink()
    _clean_auto_transcripts(case_dir)


def _clean_auto_transcripts(case_dir: Path) -> None:
    """Remove Fluent launcher's timestamped duplicate transcripts.

    The journal-owned transcripts under ``logs`` are the case evidence.  Fluent's
    Windows launcher additionally creates ``fluent-*.trn`` in the working
    directory; those duplicates are not part of the artifact contract and would
    otherwise accumulate across resumable runs.
    """
    for path in case_dir.glob("fluent-*.trn"):
        if path.is_file():
            path.unlink()


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _execute(
    command: Sequence[str],
    *,
    case_dir: Path,
    console_log: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    console_log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with console_log.open("w", encoding="utf-8", errors="replace", newline="\n") as output:
        process = subprocess.Popen(
            list(command),
            cwd=case_dir,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
            shell=False,
        )
        timed_out = False
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)
            return_code = process.returncode if process.returncode is not None else -1
    return {
        "command": list(command),
        "returnCode": return_code,
        "timedOut": timed_out,
        "durationSeconds": round(time.monotonic() - started, 3),
        "consoleLog": console_log.relative_to(case_dir).as_posix(),
    }


def _console_diagnostics(path: Path, *, require_v211_banner: bool) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    diagnostics = [name for name, pattern in FATAL_PATTERNS.items() if pattern.search(text)]
    if require_v211_banner and ("ANSYS Fluent 2021 R1" not in text or "Build Id: 10179" not in text):
        diagnostics.append("wrong-or-unverified-fluent-build")
    return sorted(set(diagnostics))


def _ordered_transcripts(case_dir: Path) -> list[Path]:
    base = case_dir / "logs" / "fluent.trn"
    extensions = sorted((case_dir / "logs").glob("fluent-extension-*.trn"))
    return ([base] if base.is_file() else []) + extensions


def _authority(manifest: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    configured = manifest["authority"]
    values = [configured.get(key) for key in ("manualBaselineId", "manualCd", "manualCDF", "manualTolerance")]
    if any(value is None for value in values) or not parsed.get("coefficient"):
        return {
            "authoritative": False,
            "status": "unverified-until-manual-baseline-comparison",
            "reason": "Set manualBaselineId, manualCd, manualCDF, and manualTolerance after the approved GUI comparison.",
        }
    coefficient = parsed["coefficient"]
    tolerance = float(values[3])
    delta_cd = abs(float(coefficient["Cd"]) - float(values[1]))
    delta_cdf = abs(float(coefficient["C_DF"]) - float(values[2]))
    passed = delta_cd <= tolerance and delta_cdf <= tolerance
    return {
        "authoritative": passed,
        "status": "manual-baseline-within-tolerance" if passed else "manual-baseline-outside-tolerance",
        "manualBaselineId": values[0],
        "absoluteTolerance": tolerance,
        "absoluteDelta": {"Cd": delta_cd, "C_DF": delta_cdf},
    }


def _write_summary(path: Path, report: dict[str, Any]) -> None:
    coefficient = report.get("parsed", {}).get("coefficient") or {}
    content = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><title>MECar Fluent 2D report</title>
<body><h1>{html.escape(str(report['caseId']))}</h1>
<dl><dt>Process</dt><dd>{html.escape(str(report['process']['passed']))}</dd>
<dt>Engineering gate</dt><dd>{html.escape(str(report['engineering']['passed']))}</dd>
<dt>Authoritative coefficient</dt><dd>{html.escape(str(report['authority']['authoritative']))}</dd>
<dt>Cd</dt><dd>{html.escape(str(coefficient.get('Cd')))}</dd>
<dt>C_DF (downforce positive)</dt><dd>{html.escape(str(coefficient.get('C_DF')))}</dd></dl>
<p>Axes: +x freestream, +y up. Raw force is force on body by fluid. Cd=Fx/(qA); C_DF=-Fy/(qA).</p>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def run_case(
    manifest_path: str | Path,
    runtime_root: str | Path,
    *,
    fluent_executable: str | Path | None = None,
    timeout_seconds: int = 7200,
    resume: bool = True,
    prepare_only: bool = False,
    command_override: Sequence[str] | None = None,
) -> dict[str, Any]:
    data, source_manifest = load_manifest(manifest_path)
    runtime = Path(runtime_root).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    case_dir = resolve_under(runtime, Path("cases") / data["caseId"], field="runtime case")
    report_path = case_dir / "reports" / "report.json"
    if resume and report_path.is_file():
        try:
            previous = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            previous = None
        if isinstance(previous, dict) and _verified_resume(case_dir, data, previous):
            return {**previous, "resumedSkipped": True}

    descriptor, lock = _acquire_lock(case_dir)
    try:
        for subdirectory in ("input", "journal", "logs", "reports", "artifacts"):
            (case_dir / subdirectory).mkdir(parents=True, exist_ok=True)
        _clean_run_outputs(case_dir)
        atomic_write_json(case_dir / "resolved-manifest.json", data)
        mesh_quality = build_mesh(data, source_manifest.parent, case_dir)
        journal_path = case_dir / "journal" / "run.jou"
        journal_path.write_text(build_journal(data, case_dir), encoding="ascii", newline="\n")
        if prepare_only:
            prepared = {
                "caseId": data["caseId"],
                "manifestHash": manifest_hash(data),
                "caseDirectory": str(case_dir),
                "prepared": True,
                "meshQuality": mesh_quality,
            }
            atomic_write_json(case_dir / "status.json", prepared)
            return prepared

        executable = None if command_override else discover_fluent(fluent_executable)
        if command_override:
            base_command = list(command_override)
        else:
            precision = "2ddp" if data["solver"]["precision"] == "double" else "2d"
            base_command = [str(executable), precision, "-gu", f'-t{data["solver"]["threads"]}', "-i", str(journal_path)]
        phases = [
            _execute(base_command, case_dir=case_dir, console_log=case_dir / "logs" / "console-base.log", timeout_seconds=timeout_seconds)
        ]
        console_diagnostics = _console_diagnostics(
            case_dir / "logs" / "console-base.log", require_v211_banner=command_override is None
        )
        transcript_paths = _ordered_transcripts(case_dir)
        if not transcript_paths:
            raise SolverError("Fluent produced no transcript; process completion cannot be trusted")
        parsed = parse_transcripts(transcript_paths, data)
        process_passed = (
            phases[-1]["returnCode"] == 0
            and not phases[-1]["timedOut"]
            and parsed["completedMarker"]
            and not parsed["fatalDiagnostics"]
            and not console_diagnostics
        )
        write_monitor_csvs(parsed, case_dir / "reports")
        engineering = evaluate_engineering_gates(
            data,
            parsed,
            present_artifacts=_present_artifacts(case_dir, include_generated_report=True),
            mesh_quality=mesh_quality,
        )

        total_iterations = int(data["iterations"]["warmup"]) + int(data["iterations"]["secondOrder"])
        extension_index = 0
        while (
            process_passed
            and not engineering["passed"]
            and data["iterations"]["autoExtend"]
            and total_iterations < int(data["iterations"]["hardMaximum"])
            and not engineering["checks"]["artifacts"]["missing"]
        ):
            extension_index += 1
            count = min(
                int(data["iterations"]["extensionChunk"]),
                int(data["iterations"]["hardMaximum"]) - total_iterations,
            )
            for image in ("vector.png", "velocity-contour.png", "pressure-contour.png"):
                image_path = case_dir / "artifacts" / image
                if image_path.is_file():
                    image_path.unlink()
            extension_path = case_dir / "journal" / f"extension-{extension_index:03d}.jou"
            extension_path.write_text(
                build_extension_journal(
                    data,
                    case_dir,
                    extension_index=extension_index,
                    start_iteration=total_iterations,
                    count=count,
                ),
                encoding="ascii",
                newline="\n",
            )
            if command_override:
                # Test transports are single-shot by design; no fabricated
                # extension is allowed to turn a failed engineering gate green.
                break
            command = [str(executable), base_command[1], "-gu", base_command[3], "-i", str(extension_path)]
            phase = _execute(
                command,
                case_dir=case_dir,
                console_log=case_dir / "logs" / f"console-extension-{extension_index:03d}.log",
                timeout_seconds=timeout_seconds,
            )
            phases.append(phase)
            console_diagnostics.extend(
                _console_diagnostics(case_dir / "logs" / f"console-extension-{extension_index:03d}.log", require_v211_banner=True)
            )
            transcript_paths = _ordered_transcripts(case_dir)
            parsed = parse_transcripts(transcript_paths, data)
            process_passed = (
                phase["returnCode"] == 0
                and not phase["timedOut"]
                and parsed["completedMarker"]
                and not parsed["fatalDiagnostics"]
                and not console_diagnostics
            )
            total_iterations += count
            write_monitor_csvs(parsed, case_dir / "reports")
            engineering = evaluate_engineering_gates(
                data,
                parsed,
                present_artifacts=_present_artifacts(case_dir, include_generated_report=True),
                mesh_quality=mesh_quality,
            )

        report = {
            "schemaVersion": "mecar.fluent2d.result/v1",
            "caseId": data["caseId"],
            "manifestHash": manifest_hash(data),
            "process": {"passed": process_passed, "phases": phases, "diagnostics": sorted(set(console_diagnostics + parsed["fatalDiagnostics"]))},
            "engineering": engineering,
            "authority": _authority(data, parsed),
            "iterationsCompleted": total_iterations,
            "parsed": parsed,
            "meshQuality": mesh_quality,
            "resumedSkipped": False,
        }
        _write_summary(case_dir / "reports" / "summary.html", report)
        atomic_write_json(report_path, report)
        checksums = {
            name: sha256_file(_case_path(case_dir, name))
            for name in data["artifacts"]["required"]
            if name != "report.json" and _case_path(case_dir, name).is_file()
        }
        report["artifactChecksums"] = checksums
        atomic_write_json(report_path, report)
        atomic_write_json(case_dir / "status.json", {"caseId": data["caseId"], "processPassed": process_passed, "engineeringPassed": engineering["passed"], "authoritative": report["authority"]["authoritative"]})
        return report
    except Fluent2DError:
        raise
    finally:
        _clean_auto_transcripts(case_dir)
        _release_lock(descriptor, lock)


def run_sweep(
    manifest_paths: Sequence[str | Path],
    runtime_root: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    rows = []
    for manifest_path in manifest_paths:
        try:
            result = run_case(manifest_path, runtime_root, **kwargs)
            rows.append({
                "manifest": str(manifest_path),
                "caseId": result["caseId"],
                "processPassed": result.get("process", {}).get("passed"),
                "engineeringPassed": result.get("engineering", {}).get("passed"),
                "resumedSkipped": result.get("resumedSkipped", False),
                "error": None,
            })
        except Exception as exc:
            rows.append({"manifest": str(manifest_path), "caseId": None, "processPassed": False, "engineeringPassed": False, "resumedSkipped": False, "error": f"{type(exc).__name__}: {exc}"})
    summary = {
        "schemaVersion": "mecar.fluent2d.sweep/v1",
        "caseCount": len(rows),
        "completed": sum(1 for row in rows if row["engineeringPassed"]),
        "failed": sum(1 for row in rows if not row["engineeringPassed"]),
        "cases": rows,
    }
    output = Path(runtime_root).resolve() / "sweep-summary.json"
    atomic_write_json(output, summary)
    return summary
