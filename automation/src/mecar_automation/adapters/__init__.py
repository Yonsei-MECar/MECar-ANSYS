from .base import AdapterOutcome, AnalysisAdapter, PreparedRun
from .dummy import DummyAdapter
from .fluent import FluentV211Adapter
from .mapdl import MapdlV211Adapter


def default_adapters() -> dict[str, AnalysisAdapter]:
    adapters: list[AnalysisAdapter] = [DummyAdapter(), MapdlV211Adapter(), FluentV211Adapter()]
    return {adapter.name: adapter for adapter in adapters}


__all__ = [
    "AdapterOutcome",
    "AnalysisAdapter",
    "PreparedRun",
    "DummyAdapter",
    "MapdlV211Adapter",
    "FluentV211Adapter",
    "default_adapters",
]

