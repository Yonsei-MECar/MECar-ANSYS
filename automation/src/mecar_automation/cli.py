from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

from .agent import AgentLoop, AgentSettings, request_agent_stop
from .artifacts import ArchiveRoute
from .engine import AutomationEngine
from .errors import AutomationError
from .health import build_health_report
from .license_health import LicenseProbeSettings
from .notifications import FakeSender, OutboxDrainer, RecipientPolicy, SmtpSender, WindowsCredentialResolver
from .supervisor import ResourceCapacity
from .util import load_json, resolve_within


def _default_profiles() -> Path:
    return Path(__file__).resolve().parent / "default_profiles"


def _load_config(path: Path | None) -> dict:
    if path is None:
        return {
            "external_execution_enabled": False,
            "external_archive_enabled": False,
            "external_license_probe_enabled": False,
            "minimum_free_disk_mb": 64,
            "resources": {"cpu": 1, "memory_mb": 4096, "licenses": {}},
            "recipient_policy": {"version": "1", "allowed_domains": [], "allowed_addresses": []},
            "notification": {"adapter": "fake"},
            "artifacts": {"local_root": "artifacts", "archive": {"adapter": "disabled"}},
            "license_probe": {"adapter": "disabled"},
            "agent": {"enabled": False, "poll_interval_sec": 5.0},
        }
    return load_json(path)


def _engine(args: argparse.Namespace, config: dict) -> AutomationEngine:
    capacity_config = config.get("resources", {})
    if not isinstance(capacity_config, dict):
        raise ValueError("resources must be an object")
    cpu = capacity_config.get("cpu", 1)
    memory_mb = capacity_config.get("memory_mb", 4096)
    license_capacity = capacity_config.get("licenses", {})
    if isinstance(cpu, bool) or not isinstance(cpu, int) or cpu < 1:
        raise ValueError("resources.cpu must be a positive integer")
    if isinstance(memory_mb, bool) or not isinstance(memory_mb, int) or memory_mb < 1:
        raise ValueError("resources.memory_mb must be a positive integer")
    if not isinstance(license_capacity, dict) or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in license_capacity.values()
    ):
        raise ValueError("resources.licenses values must be non-negative integers")
    capacity = ResourceCapacity(
        cpu=cpu,
        memory_mb=memory_mb,
        licenses={str(k): value for k, value in license_capacity.items()},
    )
    runtime_root = Path(args.runtime_root).resolve()
    artifacts_config = config.get("artifacts", {})
    if not isinstance(artifacts_config, dict):
        raise ValueError("artifacts must be an object")
    local_root_value = artifacts_config.get("local_root", "artifacts")
    if not isinstance(local_root_value, str) or not local_root_value:
        raise ValueError("artifacts.local_root must be a non-empty relative path")
    if Path(local_root_value).is_absolute():
        raise ValueError("artifacts.local_root must stay relative to runtime-root")
    artifact_root = resolve_within(runtime_root, local_root_value)
    external_archive_enabled = config.get("external_archive_enabled", False)
    if not isinstance(external_archive_enabled, bool):
        raise ValueError("external_archive_enabled must be a boolean")
    archive_route = ArchiveRoute.from_config(
        artifacts_config.get("archive"),
        machine_enabled=external_archive_enabled,
    )
    external_execution_enabled = config.get("external_execution_enabled", False)
    if not isinstance(external_execution_enabled, bool):
        raise ValueError("external_execution_enabled must be a boolean")
    return AutomationEngine(
        runtime_root,
        Path(args.profiles),
        external_execution_enabled=external_execution_enabled,
        capacity=capacity,
        minimum_free_disk_mb=int(config.get("minimum_free_disk_mb", 64)),
        notification_policy_version=str(config.get("recipient_policy", {}).get("version", "1")),
        artifact_root=artifact_root,
        archive_route=archive_route,
    )


def _policy(config: dict) -> RecipientPolicy:
    raw = config.get("recipient_policy", {})
    return RecipientPolicy(
        version=str(raw.get("version", "1")),
        allowed_domains=frozenset(str(value).lower() for value in raw.get("allowed_domains", [])),
        allowed_addresses=frozenset(str(value).lower() for value in raw.get("allowed_addresses", [])),
        max_recipients=int(raw.get("max_recipients", 20)),
    )


def _sender(config: dict):
    notification = config.get("notification", {"adapter": "fake"})
    if notification.get("adapter", "fake") == "fake":
        return FakeSender()
    if notification.get("adapter") != "smtp":
        raise ValueError("notification.adapter must be fake or smtp")

    external_notification_enabled = config.get("external_notification_enabled", False)
    if not isinstance(external_notification_enabled, bool):
        raise ValueError("external_notification_enabled must be a boolean")
    return SmtpSender(
        notification,
        WindowsCredentialResolver(),
        enabled=external_notification_enabled,
    )


def _license_settings(config: dict) -> LicenseProbeSettings:
    machine_enabled = config.get("external_license_probe_enabled", False)
    if not isinstance(machine_enabled, bool):
        raise ValueError("external_license_probe_enabled must be a boolean")
    return LicenseProbeSettings.from_config(config.get("license_probe"), machine_enabled=machine_enabled)


def _drain_cycle(
    engine: AutomationEngine,
    config: dict,
    *,
    max_jobs: int,
    max_attempts: int,
    max_archive_operations: int,
) -> dict:
    intake = [result.__dict__ for result in engine.hotfolder.scan()]
    recovery = engine.reconcile(max_attempts=max_attempts)
    outbox_recovery = engine.database.reconcile_outbox()
    jobs = [
        {"job_id": result["job_id"], "state": result["state"]}
        for result in engine.drain_jobs(max_jobs)
    ]
    archive_recovery = engine.reconcile_archives()
    archive = engine.drain_archives(max_archive_operations)
    outbox = OutboxDrainer(engine.database, _sender(config), _policy(config)).drain()
    return {
        "intake": intake,
        "recovery": recovery,
        "outbox_recovery": outbox_recovery,
        "jobs": jobs,
        "archive_recovery": archive_recovery,
        "archive": archive,
        "outbox": outbox,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mecar-analysis")
    parser.add_argument("--runtime-root", default=r"C:\MECarRuntime\ansys-automation")
    parser.add_argument("--profiles", default=str(_default_profiles()))
    parser.add_argument("--config", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("manifest", type=Path)
    commands.add_parser("list")
    show = commands.add_parser("show")
    show.add_argument("job_id")
    cancel = commands.add_parser("cancel")
    cancel.add_argument("job_id")
    retry = commands.add_parser("retry")
    retry.add_argument("job_id")
    commands.add_parser("pause")
    commands.add_parser("resume")
    drain = commands.add_parser("drain")
    drain.add_argument("--max-jobs", type=int, default=100)
    drain.add_argument("--max-attempts", type=int, default=2)
    drain.add_argument("--max-archive-operations", type=int, default=100)
    archive = commands.add_parser("archive")
    archive.add_argument("--max-operations", type=int, default=100)
    archive.add_argument("--stale-after-sec", type=float, default=300.0)
    archive_retry = commands.add_parser("archive-retry")
    archive_retry.add_argument("--job-id")
    agent = commands.add_parser("agent")
    agent.add_argument("--once", action="store_true")
    commands.add_parser("agent-stop")
    verify = commands.add_parser("verify")
    verify.add_argument("--job-id")
    commands.add_parser("health")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = _load_config(args.config)
        engine = _engine(args, config)
        command = args.command
        if command == "submit":
            result = engine.submit(load_json(args.manifest))
            output = {"job_id": result.job_id, "disposition": result.disposition}
        elif command == "list":
            output = engine.database.list_jobs()
        elif command == "show":
            output = engine.database.show_job(args.job_id)
        elif command == "cancel":
            output = {"job_id": args.job_id, "state": engine.database.request_cancel(args.job_id)}
        elif command == "retry":
            output = {"job_id": args.job_id, "state": engine.database.retry(args.job_id)}
        elif command == "pause":
            output = {"dispatcher": engine.database.set_paused(True)}
        elif command == "resume":
            output = {"dispatcher": engine.database.set_paused(False)}
        elif command == "drain":
            with engine.dispatcher_lock:
                output = _drain_cycle(
                    engine,
                    config,
                    max_jobs=args.max_jobs,
                    max_attempts=args.max_attempts,
                    max_archive_operations=args.max_archive_operations,
                )
        elif command == "archive":
            recovery = engine.reconcile_archives(stale_after_sec=args.stale_after_sec)
            output = {"recovery": recovery, "archive": engine.drain_archives(args.max_operations)}
        elif command == "archive-retry":
            output = {"archive": engine.retry_archives(args.job_id)}
        elif command == "agent":
            settings = AgentSettings.from_config(config.get("agent"))
            stop_event = threading.Event()
            prior_handlers: dict[int, object] = {}

            def request_stop(signum, frame) -> None:
                del signum, frame
                stop_event.set()

            for signal_name in ("SIGINT", "SIGTERM"):
                signal_value = getattr(signal, signal_name, None)
                if signal_value is not None:
                    prior_handlers[signal_value] = signal.getsignal(signal_value)
                    signal.signal(signal_value, request_stop)
            try:
                loop = AgentLoop(
                    engine,
                    settings,
                    lambda: _drain_cycle(
                        engine,
                        config,
                        max_jobs=settings.max_jobs_per_cycle,
                        max_attempts=settings.max_stale_attempts,
                        max_archive_operations=settings.max_archive_operations_per_cycle,
                    ),
                    stop_event=stop_event,
                )
                output = loop.run(once=args.once)
            finally:
                for signal_value, prior in prior_handlers.items():
                    signal.signal(signal_value, prior)
            print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
            return 0 if output.get("last_error_code") is None else 2
        elif command == "agent-stop":
            output = request_agent_stop(engine.runtime_root)
        elif command == "verify":
            output = engine.verify(args.job_id)
            print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
            return 0 if output["valid"] and output["database"]["integrity"] == "ok" else 2
        elif command == "health":
            output = build_health_report(engine, config, _license_settings(config))
            print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
            return 0 if output["status"] == "OK" else 2
        else:
            parser.error(f"Unknown command: {command}")
            return 2
        print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    except (AutomationError, KeyError, ValueError, OSError) as exc:
        code = exc.code if isinstance(exc, AutomationError) else type(exc).__name__.upper()
        print(json.dumps({"error": code, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
