from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from .adapters.base import PreparedRun
from .errors import (
    DiskReserveUnavailable,
    ResourceCapacityUnavailable,
    ResourceUnavailable,
    ResourceWaitTimeout,
)


@dataclass(frozen=True)
class ResourceCapacity:
    cpu: int = 1
    memory_mb: int = 4096
    licenses: dict[str, int] = field(default_factory=dict)


class ResourceGate:
    def __init__(self, capacity: ResourceCapacity):
        self.capacity = capacity
        self._available_cpu = capacity.cpu
        self._available_memory = capacity.memory_mb
        self._available_licenses = dict(capacity.licenses)
        self._condition = threading.Condition()

    @contextmanager
    def reserve(self, request: dict, wait_timeout: float = 5.0) -> Iterator[None]:
        cpu = int(request.get("cpu", 1))
        memory = int(request.get("memory_mb", 256))
        licenses = {str(key): int(value) for key, value in request.get("licenses", {}).items()}
        if cpu > self.capacity.cpu or memory > self.capacity.memory_mb:
            raise ResourceCapacityUnavailable("Job request exceeds configured CPU or memory capacity")
        for feature, count in licenses.items():
            if count > self.capacity.licenses.get(feature, 0):
                raise ResourceCapacityUnavailable(f"License capacity is not configured for {feature}")
        deadline = time.monotonic() + wait_timeout
        with self._condition:
            while not self._fits(cpu, memory, licenses):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ResourceWaitTimeout("Timed out waiting for the local resource/license gate")
                self._condition.wait(min(remaining, 0.25))
            self._available_cpu -= cpu
            self._available_memory -= memory
            for feature, count in licenses.items():
                self._available_licenses[feature] -= count
        try:
            yield
        finally:
            with self._condition:
                self._available_cpu += cpu
                self._available_memory += memory
                for feature, count in licenses.items():
                    self._available_licenses[feature] += count
                self._condition.notify_all()

    def snapshot(self) -> dict:
        with self._condition:
            return {
                "capacity": {
                    "cpu": self.capacity.cpu,
                    "memory_mb": self.capacity.memory_mb,
                    "licenses": dict(self.capacity.licenses),
                },
                "available": {
                    "cpu": self._available_cpu,
                    "memory_mb": self._available_memory,
                    "licenses": dict(self._available_licenses),
                },
            }

    def _fits(self, cpu: int, memory: int, licenses: dict[str, int]) -> bool:
        return (
            cpu <= self._available_cpu
            and memory <= self._available_memory
            and all(count <= self._available_licenses.get(feature, 0) for feature, count in licenses.items())
        )


class SingletonFileLock:
    """OS-released non-blocking lock preventing multiple local dispatcher processes."""

    def __init__(self, path: Path):
        self.path = path
        self._stream = None

    def __enter__(self) -> "SingletonFileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self._stream.write(b"0")
            self._stream.flush()
        self._stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self._stream.close()
            self._stream = None
            raise ResourceUnavailable("Another dispatcher already owns the runtime lock") from exc
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._stream is None:
            return
        self._stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        self._stream.close()
        self._stream = None


@dataclass
class ProcessResult:
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    duration_sec: float
    pid: int | None
    adapter_settings: dict = field(default_factory=dict)


class ProcessSupervisor:
    def __init__(self, gate: ResourceGate, *, minimum_free_disk_mb: int = 256):
        self.gate = gate
        self.minimum_free_disk_mb = minimum_free_disk_mb

    def run(
        self,
        prepared: PreparedRun,
        workdir: Path,
        *,
        timeout_sec: float,
        resources: dict,
        cancel_check: Callable[[], bool] | None = None,
        on_started: Callable[[int], None] | None = None,
        adapter_settings: dict | None = None,
    ) -> ProcessResult:
        workdir.mkdir(parents=True, exist_ok=True)
        free_mb = shutil.disk_usage(workdir).free // (1024 * 1024)
        if free_mb < self.minimum_free_disk_mb:
            raise DiskReserveUnavailable(
                f"Free disk space {free_mb} MiB is below reserve {self.minimum_free_disk_mb} MiB"
            )
        stdout_path = workdir / "stdout.log"
        stderr_path = workdir / "stderr.log"
        start = time.monotonic()
        with self.gate.reserve(resources):
            environment = os.environ.copy()
            environment.update(prepared.environment)
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                process = subprocess.Popen(
                    list(prepared.command),
                    cwd=workdir,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=stdout,
                    stderr=stderr,
                    shell=False,
                    creationflags=flags,
                    start_new_session=(os.name != "nt"),
                )
                if on_started:
                    on_started(process.pid)
                timed_out = False
                cancelled = False
                while process.poll() is None:
                    if cancel_check and cancel_check():
                        cancelled = True
                        self._terminate_tree(process)
                        break
                    if time.monotonic() - start >= timeout_sec:
                        timed_out = True
                        self._terminate_tree(process)
                        break
                    time.sleep(0.025)
                try:
                    exit_code = process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    self._kill_tree(process)
                    exit_code = process.wait(timeout=2.0)
        return ProcessResult(
            exit_code=exit_code,
            timed_out=timed_out,
            cancelled=cancelled,
            duration_sec=round(time.monotonic() - start, 6),
            pid=process.pid,
            adapter_settings=dict(adapter_settings or {}),
        )

    @staticmethod
    def _terminate_tree(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=0.75)
        except subprocess.TimeoutExpired:
            ProcessSupervisor._kill_tree(process)

    @staticmethod
    def _kill_tree(process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)


def process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True
