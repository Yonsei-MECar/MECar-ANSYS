from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import Fluent2DError
from .manifest import load_manifest
from .runner import discover_fluent, run_case, run_sweep
from .sweep import generate_sweep_manifests


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MECar Fluent 2021 R1 2D fail-closed runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate inputs without writing runtime files")
    validate.add_argument("manifest", type=Path)

    environment = subparsers.add_parser("verify-environment", help="verify local Fluent and pinned Gmsh")
    environment.add_argument("--fluent-exe", type=Path)

    for name in ("prepare", "run"):
        command = subparsers.add_parser(name)
        command.add_argument("manifest", type=Path)
        command.add_argument("--runtime-root", type=Path, default=Path(r"C:\MECarRuntime\fluent"))
        command.add_argument("--fluent-exe", type=Path)
        command.add_argument("--timeout-seconds", type=int, default=7200)
        command.add_argument("--no-resume", action="store_true")

    sweep = subparsers.add_parser("sweep", help="run independent manifests; one failure does not stop the others")
    sweep.add_argument("manifest_dir", type=Path)
    sweep.add_argument("--runtime-root", type=Path, default=Path(r"C:\MECarRuntime\fluent"))
    sweep.add_argument("--fluent-exe", type=Path)
    sweep.add_argument("--timeout-seconds", type=int, default=7200)
    sweep.add_argument("--no-resume", action="store_true")
    generate = subparsers.add_parser("generate-sweep", help="expand a decision-ready plan into isolated case manifests")
    generate.add_argument("base_manifest", type=Path)
    generate.add_argument("plan", type=Path)
    generate.add_argument("output_root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            data, path = load_manifest(args.manifest)
            result = {"valid": True, "caseId": data["caseId"], "manifest": str(path)}
        elif args.command == "verify-environment":
            executable = discover_fluent(args.fluent_exe)
            try:
                import gmsh  # type: ignore
            except (ImportError, OSError) as exc:
                raise Fluent2DError("gmsh is not importable; run scripts/setup_gmsh.ps1") from exc
            if gmsh.__version__ != "4.13.1":
                raise Fluent2DError(f"expected gmsh 4.13.1, found {gmsh.__version__}")
            result = {"valid": True, "fluentExecutable": str(executable), "gmshVersion": gmsh.__version__}
        elif args.command in {"prepare", "run"}:
            result = run_case(
                args.manifest,
                args.runtime_root,
                fluent_executable=args.fluent_exe,
                timeout_seconds=args.timeout_seconds,
                resume=not args.no_resume,
                prepare_only=args.command == "prepare",
            )
        elif args.command == "generate-sweep":
            result = generate_sweep_manifests(args.base_manifest, args.plan, args.output_root)
        else:
            manifests = sorted(args.manifest_dir.glob("*.json"))
            if not manifests:
                raise Fluent2DError(f"no JSON manifests found in {args.manifest_dir}")
            result = run_sweep(
                manifests,
                args.runtime_root,
                fluent_executable=args.fluent_exe,
                timeout_seconds=args.timeout_seconds,
                resume=not args.no_resume,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if args.command == "run":
            return 0 if result.get("process", {}).get("passed") and result.get("engineering", {}).get("passed") else 2
        if args.command == "sweep":
            return 0 if result["failed"] == 0 else 2
        if args.command == "generate-sweep":
            return 0 if result["complete"] else 2
        return 0
    except Fluent2DError as exc:
        payload = {"error": exc.code, "message": str(exc), "hint": getattr(exc, "hint", None)}
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
