from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PreparedRun:
    command: tuple[str, ...]
    environment: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterOutcome:
    succeeded: bool
    reason_code: str
    metrics: dict[str, Any]
    artifacts: tuple[tuple[str, Path], ...]


class AnalysisAdapter(ABC):
    name: str

    @abstractmethod
    def prepare(
        self,
        manifest: dict[str, Any],
        profile: dict[str, Any],
        workdir: Path,
        *,
        external_execution_enabled: bool,
    ) -> PreparedRun:
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, workdir: Path, process: Any) -> AdapterOutcome:
        raise NotImplementedError

