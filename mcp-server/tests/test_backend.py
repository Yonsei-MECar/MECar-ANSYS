from pathlib import Path

import pytest

from ansys_mcp_server.backend import AnsysBackend, MapdlLaunchError
from ansys_mcp_server.config import Settings


def backend(tmp_path: Path) -> AnsysBackend:
    cfg = Settings(
        211,
        tmp_path / "v211",
        tmp_path,
        tmp_path / "runs",
        tmp_path / "RunWB2.exe",
        tmp_path / "ANSYS211.exe",
        True,
        True,
    )
    return AnsysBackend(cfg)


def test_status_without_ansys(tmp_path: Path):
    status = backend(tmp_path).status()
    assert status["connected"] is False
    assert status["ansys_version"] == 211


def test_invalid_mesh_size_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError):
        backend(tmp_path).mesh(0)


def test_raw_apdl_requires_connection(tmp_path: Path):
    with pytest.raises(RuntimeError):
        backend(tmp_path).run_apdl("/PREP7")


def test_post_processing_reads_last_result_set(tmp_path: Path):
    np = pytest.importorskip("numpy")

    class FakeResult:
        nsets = 3
        requested = None

        def principal_nodal_stress(self, index):
            self.requested = index
            return np.array([10, 20]), np.array([[1, 2, 3, 4, 5], [1, 2, 3, 4, 9]], dtype=float)

    class FakeMapdl:
        result = FakeResult()

        def post1(self):
            pass

        def set(self, value):
            assert value == "LAST"

    target = backend(tmp_path)
    target._mapdl = FakeMapdl()
    value = target.get_stress()
    assert target._mapdl.result.requested == 2
    assert value["maximum"] == 9.0
    assert value["node"] == 20


def test_mesh_does_not_expand_current_selection(tmp_path: Path):
    class FakeMesh:
        n_elem = 12

    class FakeMapdl:
        mesh = FakeMesh()
        calls = []

        def prep7(self):
            self.calls.append("prep7")

        def esize(self, size):
            self.calls.append(("esize", size))

        def vmesh(self, selection):
            self.calls.append(("vmesh", selection))
            return "meshed"

    target = backend(tmp_path)
    target._mapdl = FakeMapdl()
    value = target.mesh(0.005)
    assert "allsel" not in target._mapdl.calls
    assert value["element_count"] == 12


def test_live_smoke_solves_and_checks_scalar_result(tmp_path: Path):
    class FakeMapdl:
        calls = []

        def __getattr__(self, name):
            def call(*args):
                self.calls.append((name, args))
                if name == "solve":
                    return "SOLVE COMPLETED"
                if name == "get_value":
                    return 5.0e-6
                return None

            return call

    target = backend(tmp_path)
    target._mapdl = FakeMapdl()
    result = target.live_smoke()
    assert result["displacement"] == pytest.approx(5.0e-6)
    assert result["relative_error"] == pytest.approx(0.0)
    assert ("get_value", ("NODE", 2, "U", "X")) in target._mapdl.calls


def test_launch_failure_hint_sanitizes_license_details(tmp_path: Path):
    target = backend(tmp_path)
    launch_location = target.settings.run_location / "launch-current"
    launch_location.mkdir(parents=True)
    log = launch_location / ".__tmp__.out"
    log.write_text(
        "License server machine is down or not responding. License path: secret-host.example;",
        encoding="utf-8",
    )
    code, hint = target._classify_launch_failure(RuntimeError("launch failed"), launch_location)
    assert code == "LICENSE_UNAVAILABLE"
    assert "license server is unavailable" in hint
    assert "secret-host" not in hint


def test_launch_passes_exec_file_without_version(tmp_path: Path, monkeypatch):
    target = backend(tmp_path)
    target.settings.mapdl_exe.parent.mkdir(parents=True, exist_ok=True)
    target.settings.mapdl_exe.write_bytes(b"fixture")
    captured = {}

    class FakeMapdl:
        name = "fixture"

    def fake_launch_mapdl(**kwargs):
        captured.update(kwargs)
        return FakeMapdl()

    monkeypatch.setattr("ansys.mapdl.core.launch_mapdl", fake_launch_mapdl)
    result = target.launch(nproc=1)
    assert result["connected"] is True
    assert captured["exec_file"] == str(target.settings.mapdl_exe)
    assert "version" not in captured
    assert Path(captured["run_location"]).parent == target.settings.run_location


def test_current_configuration_error_wins_over_stale_license_log(tmp_path: Path, monkeypatch):
    target = backend(tmp_path)
    target.settings.mapdl_exe.parent.mkdir(parents=True, exist_ok=True)
    target.settings.mapdl_exe.write_bytes(b"fixture")
    target.settings.run_location.mkdir()
    (target.settings.run_location / ".__tmp__.out").write_text(
        "License server machine is down or not responding", encoding="utf-8"
    )

    def fail_launch(**_kwargs):
        raise ValueError("Configuration error: Cannot specify both 'exec_file' and 'version'.")

    monkeypatch.setattr("ansys.mapdl.core.launch_mapdl", fail_launch)
    with pytest.raises(MapdlLaunchError) as caught:
        target.launch()
    assert caught.value.code == "BAD_CONFIGURATION"
    assert "LICENSE_UNAVAILABLE" not in str(caught.value)


def test_open_project_uses_self_terminating_batch_journal(tmp_path: Path):
    target = backend(tmp_path)
    project = tmp_path / "model.wbpj"
    project.write_text("placeholder", encoding="utf-8")
    captured = {}

    def fake_run(args, timeout):
        captured["args"] = args
        captured["timeout"] = timeout
        journal = Path(args[2])
        captured["journal_text"] = journal.read_text(encoding="utf-8")
        return {"ok": True, "exit_code": 0}

    target._run_workbench = fake_run
    result = target.open_project("model.wbpj", timeout_seconds=17)
    assert result["ok"] is True
    assert captured["args"][:2] == ["-B", "-R"]
    assert "Open(FilePath=" in captured["journal_text"]
    assert captured["timeout"] == 17
    assert not Path(captured["args"][2]).exists()


@pytest.mark.parametrize("analysis_type", ["MODAL", "BUCKLE", "HARMIC"])
def test_generic_results_reject_analysis_specific_scalars(tmp_path: Path, analysis_type: str):
    target = backend(tmp_path)
    target._mapdl = object()
    target._last_result = {"analysis_type": analysis_type}
    with pytest.raises(RuntimeError, match="analysis-specific"):
        target.get_stress()
