from pathlib import Path

import pytest

from ansys_mcp_server.config import Settings


def settings(tmp_path: Path) -> Settings:
    return Settings(
        211,
        tmp_path / "v211",
        tmp_path,
        tmp_path / "runs",
        tmp_path / "RunWB2.exe",
        tmp_path / "ANSYS211.exe",
        True,
        True,
    )


def test_relative_path_stays_in_root(tmp_path: Path):
    assert settings(tmp_path).resolve_work_path("models/test.db") == (tmp_path / "models/test.db").resolve()


def test_parent_escape_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        settings(tmp_path).resolve_work_path("../outside.db")
