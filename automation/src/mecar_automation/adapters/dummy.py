from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from ..errors import ValidationError
from .base import AdapterOutcome, AnalysisAdapter, PreparedRun


_WORKER = """
import json, os, sys, time
mode = sys.argv[1]
delay = float(sys.argv[2])
if mode == 'hang':
    time.sleep(max(delay, 60.0))
elif mode == 'crash':
    os._exit(23)
elif mode == 'failure':
    with open('result.json', 'w', encoding='utf-8') as stream:
        json.dump({'outcome': 'FAILED', 'metric': 0.0}, stream)
    raise SystemExit(7)
else:
    if delay:
        time.sleep(delay)
    with open('result.json', 'w', encoding='utf-8') as stream:
        json.dump({'outcome': 'PASSED', 'metric': 42.0}, stream)
"""


class DummyAdapter(AnalysisAdapter):
    name = "dummy"

    def prepare(
        self,
        manifest: dict[str, Any],
        profile: dict[str, Any],
        workdir: Path,
        *,
        external_execution_enabled: bool,
    ) -> PreparedRun:
        del external_execution_enabled
        if profile["adapter"] != self.name or not profile["enabled"]:
            raise ValidationError("Dummy profile is disabled or has the wrong adapter")
        mode = manifest.get("parameters", {}).get("mode", "success")
        if mode not in {"success", "failure", "hang", "crash"}:
            raise ValidationError("Dummy mode must be success, failure, hang, or crash")
        delay = manifest.get("parameters", {}).get("delay_sec", 0)
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or delay < 0 or delay > 10:
            raise ValidationError("Dummy delay_sec must be between 0 and 10")
        return PreparedRun((sys.executable, "-c", _WORKER, mode, str(float(delay))))

    def evaluate(self, workdir: Path, process: Any) -> AdapterOutcome:
        artifacts: list[tuple[str, Path]] = []
        for role, name in (("solver_stdout", "stdout.log"), ("solver_stderr", "stderr.log")):
            path = workdir / name
            if path.is_file():
                artifacts.append((role, path))
        result_path = workdir / "result.json"
        if result_path.is_file():
            artifacts.append(("solver_result", result_path))
        if process.timed_out:
            return AdapterOutcome(False, "PROCESS_TIMEOUT", {}, tuple(artifacts))
        if process.cancelled:
            return AdapterOutcome(False, "PROCESS_CANCELLED", {}, tuple(artifacts))
        if process.exit_code != 0:
            code = "DUMMY_DECLARED_FAILURE" if result_path.is_file() else "PROCESS_CRASH"
            return AdapterOutcome(False, code, {}, tuple(artifacts))
        if not result_path.is_file():
            return AdapterOutcome(False, "MANDATORY_RESULT_MISSING", {}, tuple(artifacts))
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AdapterOutcome(False, "RESULT_PARSE_ERROR", {}, tuple(artifacts))
        if payload.get("outcome") != "PASSED" or not isinstance(payload.get("metric"), (int, float)):
            return AdapterOutcome(False, "ENGINEERING_CHECK_FAILED", {}, tuple(artifacts))
        return AdapterOutcome(True, "DUMMY_PASSED", {"metric": float(payload["metric"])}, tuple(artifacts))

