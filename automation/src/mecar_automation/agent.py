from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .engine import AutomationEngine
from .errors import AutomationError, ExternalExecutionDisabled, ValidationError
from .util import atomic_write_json, utc_now


@dataclass(frozen=True)
class AgentSettings:
    enabled: bool = False
    poll_interval_sec: float = 5.0
    max_jobs_per_cycle: int = 100
    max_archive_operations_per_cycle: int = 100
    max_stale_attempts: int = 2

    @classmethod
    def from_config(cls, raw: dict[str, Any] | None) -> AgentSettings:
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValidationError("agent must be an object")
        enabled = raw.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ValidationError("agent.enabled must be boolean")
        poll = raw.get("poll_interval_sec", 5.0)
        if isinstance(poll, bool) or not isinstance(poll, (int, float)) or not 0.1 <= float(poll) <= 3600:
            raise ValidationError("agent.poll_interval_sec must be from 0.1 to 3600 seconds")

        def bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
            value = raw.get(name, default)
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ValidationError(f"agent.{name} must be an integer from {minimum} to {maximum}")
            return value

        return cls(
            enabled=enabled,
            poll_interval_sec=float(poll),
            max_jobs_per_cycle=bounded_integer("max_jobs_per_cycle", 100, 1, 10000),
            max_archive_operations_per_cycle=bounded_integer(
                "max_archive_operations_per_cycle", 100, 1, 10000
            ),
            max_stale_attempts=bounded_integer("max_stale_attempts", 2, 1, 100),
        )


def request_agent_stop(runtime_root: Path, actor: str = "cli") -> dict[str, Any]:
    marker = runtime_root.resolve() / "state" / "agent.stop.json"
    payload = {"requested_at": utc_now(), "actor": actor}
    atomic_write_json(marker, payload)
    return {"state": "STOP_REQUESTED", "marker": str(marker)}


class AgentLoop:
    """Persistent single-dispatcher loop with signal/event and stop-file shutdown."""

    def __init__(
        self,
        engine: AutomationEngine,
        settings: AgentSettings,
        cycle: Callable[[], dict[str, Any]],
        *,
        stop_event: threading.Event | None = None,
    ):
        self.engine = engine
        self.settings = settings
        self.cycle = cycle
        self.stop_event = stop_event or threading.Event()
        self.status_path = engine.runtime_root / "state" / "agent.status.json"
        self.stop_path = engine.runtime_root / "state" / "agent.stop.json"

    @staticmethod
    def _cycle_summary(result: dict[str, Any]) -> dict[str, int]:
        return {
            "intake": len(result.get("intake", [])),
            "recovery": len(result.get("recovery", [])),
            "jobs": len(result.get("jobs", [])),
            "archive": len(result.get("archive", [])),
            "outbox": len(result.get("outbox", [])),
        }

    def _write_status(
        self,
        *,
        state: str,
        started_at: str,
        cycle_count: int,
        last_cycle_at: str | None,
        last_cycle_summary: dict[str, int] | None,
        last_error_code: str | None,
    ) -> dict[str, Any]:
        payload = {
            "schema_version": "1.0.0",
            "state": state,
            "pid": os.getpid(),
            "started_at": started_at,
            "updated_at": utc_now(),
            "last_cycle_at": last_cycle_at,
            "cycle_count": cycle_count,
            "last_cycle_summary": last_cycle_summary,
            "last_error_code": last_error_code,
            "poll_interval_sec": self.settings.poll_interval_sec,
            "external_execution_enabled": self.engine.external_execution_enabled,
        }
        atomic_write_json(self.status_path, payload)
        return payload

    def _stop_requested(self) -> bool:
        return self.stop_event.is_set() or self.stop_path.is_file()

    def _wait_for_next_cycle(self) -> None:
        deadline = time.monotonic() + self.settings.poll_interval_sec
        while not self._stop_requested():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.stop_event.wait(min(remaining, 1.0))

    def run(self, *, once: bool = False) -> dict[str, Any]:
        if not self.settings.enabled:
            raise ExternalExecutionDisabled("Persistent agent is disabled in app config")
        if self.stop_path.is_file():
            self.stop_path.unlink()
        started_at = utc_now()
        cycle_count = 0
        last_cycle_at: str | None = None
        last_cycle_summary: dict[str, int] | None = None
        last_error_code: str | None = None
        self._write_status(
            state="STARTING",
            started_at=started_at,
            cycle_count=0,
            last_cycle_at=None,
            last_cycle_summary=None,
            last_error_code=None,
        )
        with self.engine.dispatcher_lock:
            self._write_status(
                state="RUNNING",
                started_at=started_at,
                cycle_count=0,
                last_cycle_at=None,
                last_cycle_summary=None,
                last_error_code=None,
            )
            while not self._stop_requested():
                try:
                    result = self.cycle()
                    last_cycle_summary = self._cycle_summary(result)
                    last_error_code = None
                except Exception as exc:
                    last_cycle_summary = None
                    last_error_code = exc.code if isinstance(exc, AutomationError) else "AGENT_CYCLE_ERROR"
                cycle_count += 1
                last_cycle_at = utc_now()
                self._write_status(
                    state="RUNNING",
                    started_at=started_at,
                    cycle_count=cycle_count,
                    last_cycle_at=last_cycle_at,
                    last_cycle_summary=last_cycle_summary,
                    last_error_code=last_error_code,
                )
                if once:
                    break
                self._wait_for_next_cycle()
        if self.stop_path.is_file():
            self.stop_path.unlink()
        return self._write_status(
            state="STOPPED",
            started_at=started_at,
            cycle_count=cycle_count,
            last_cycle_at=last_cycle_at,
            last_cycle_summary=last_cycle_summary,
            last_error_code=last_error_code,
        )
