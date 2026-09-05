"""CLI smoke tests for `jps-scenarios`."""

from __future__ import annotations

import json
import pathlib

import pytest

from jupedsim_scenarios.cli import main

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "corridor_simple.json"


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "jps-scenarios" in captured.out


def test_cli_missing_subcommand():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_cli_run_missing_file(capsys):
    rc = main(["run", "/nonexistent/scenario.json"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not found" in err


def test_cli_run_without_out_reports_null_sqlite_path(capsys):
    """Without --out, the temp sqlite is deleted on exit; the summary
    must NOT advertise a path the caller can't read."""
    pytest.importorskip("jupedsim")
    rc = main(["run", str(FIXTURE), "--seed", "1"])
    assert rc == 0
    summary_line = next(
        line
        for line in reversed(capsys.readouterr().out.splitlines())
        if line.startswith("{")
    )
    summary = json.loads(summary_line)
    assert summary["sqlite_file"] is None


def test_cli_run_writes_sqlite_and_prints_summary(tmp_path, capsys):
    pytest.importorskip("jupedsim")
    target = tmp_path / "out.sqlite"
    rc = main(["run", str(FIXTURE), "--seed", "1", "--out", str(target)])
    assert rc == 0
    assert target.exists()
    # The simulation engine prints DEBUG lines to stdout above the summary;
    # the CLI emits the summary as a single line at the end, so the last
    # `{`-prefixed line is the summary regardless of any earlier brace output.
    summary_line = next(
        line
        for line in reversed(capsys.readouterr().out.splitlines())
        if line.startswith("{")
    )
    summary = json.loads(summary_line)
    assert summary["sqlite_file"] == str(target)
    assert summary["seed"] == 1
    assert summary["agents_evacuated"] > 0


def test_cli_run_rejects_bad_run_kwargs(capsys):
    pytest.importorskip("jupedsim")
    # every_nth_frame=0 must surface as a friendly exit-2, not a traceback.
    rc = main(["run", str(FIXTURE), "--every-nth-frame", "0"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "every_nth_frame" in err


def test_cli_run_failed_simulation_cleans_explicit_out(tmp_path, capsys, monkeypatch):
    """Addresses Copilot's PR #39 review: a failed simulation with
    --out must not leave a partial / misleading file at the user-chosen
    path."""
    pytest.importorskip("jupedsim")

    import jupedsim_scenarios.cli as cli_mod

    target = tmp_path / "should_not_persist.sqlite"

    # Stub a result that reports failure but still wrote a sqlite to
    # the user-chosen path (which run_scenario does today since the
    # writer is opened up front).
    class _FakeResult:
        success = False
        sqlite_file = str(target)
        metrics = {"message": "boom"}

        def cleanup(self):
            pathlib.Path(self.sqlite_file).unlink(missing_ok=True)

    target.write_bytes(b"partial")  # simulate the run having written some bytes

    def _fake_run_scenario(_scenario, **_kwargs):
        return _FakeResult()

    monkeypatch.setattr(cli_mod, "run_scenario", _fake_run_scenario)

    rc = main(["run", str(FIXTURE), "--out", str(target)])
    err = capsys.readouterr().err
    assert rc == 1
    assert "boom" in err
    assert not target.exists()  # CLI cleaned up the failed-run sqlite


def test_cli_run_surfaces_oserror_as_exit_2(tmp_path, capsys, monkeypatch):
    """OSError from run_scenario (e.g. unwritable output path) must
    not surface as a traceback — Copilot's PR #39 review."""
    pytest.importorskip("jupedsim")

    import jupedsim_scenarios.cli as cli_mod

    def _fake_run_scenario(_scenario, **_kwargs):
        raise PermissionError("simulated: unwritable path")

    monkeypatch.setattr(cli_mod, "run_scenario", _fake_run_scenario)

    rc = main(["run", str(FIXTURE), "--out", str(tmp_path / "out.sqlite")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "unwritable path" in err


def _last_json_line(out: str) -> dict:
    return json.loads(next(line for line in reversed(out.splitlines()) if line.startswith("{")))


def _export_zip(tmp_path) -> pathlib.Path:
    import zipfile

    data = json.loads(FIXTURE.read_text())
    wkt = data.pop("walkable_area_wkt")
    data["config"]["simulation_settings"]["simulationParams"]["max_simulation_time"] = 60
    archive = tmp_path / "jps_export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("config.json", json.dumps(data))
        zf.writestr("geometry.wkt", wkt)
        zf.writestr("README.md", "# run locally\n")
    return archive


def test_cli_sweep_zip_smoke(tmp_path, capsys):
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import SweepResult

    out_dir = tmp_path / "results"
    rc = main(["sweep", str(_export_zip(tmp_path)), "--seeds", "2", "--workers", "1", "--out", str(out_dir)])
    assert rc == 0
    summary = _last_json_line(capsys.readouterr().out)
    assert summary["n_trials"] == 2
    assert summary["n_failed"] == 0
    assert summary["seeds"] == [0, 1]
    assert summary["scale"] == 1.0
    assert summary["mode"] == "count"
    assert summary["wall_clock_s"] > 0
    assert sorted(p.name for p in out_dir.glob("*.sqlite")) == ["trial_00000.sqlite", "trial_00001.sqlite"]
    sweep = SweepResult.load(out_dir / "sweep.json")
    assert len(sweep) == 2
    assert sweep.meta["scale"] == 1.0
    assert sweep.meta["seeds"] == [0, 1]
    assert (out_dir / "scenario.json").exists()


def test_cli_sweep_seed_range(tmp_path, capsys):
    pytest.importorskip("jupedsim")
    out_dir = tmp_path / "results"
    rc = main(
        ["sweep", str(FIXTURE), "--seed-start", "5", "--seed-end", "6", "--scale", "2", "--out", str(out_dir)]
    )
    assert rc == 0
    summary = _last_json_line(capsys.readouterr().out)
    assert summary["seeds"] == [5, 6]
    scenario = json.loads((out_dir / "scenario.json").read_text())
    assert scenario["distributions"]["jps-distributions_0"]["parameters"]["number"] == 20


def test_cli_sweep_capacity_error_is_clean_exit(tmp_path, capsys):
    pytest.importorskip("jupedsim")
    rc = main(["sweep", str(FIXTURE), "--scale", "1000", "--out", str(tmp_path / "r")])
    err = capsys.readouterr().err
    assert rc == 3
    assert "capacity" in err
    assert "mode='flow'" in err
    assert "Traceback" not in err


def test_cli_report_smoke(tmp_path, capsys):
    pytest.importorskip("jupedsim")
    pytest.importorskip("matplotlib")
    from jupedsim_scenarios.report import (
        SECTION_ARRIVAL,
        SECTION_DENSITY,
        SECTION_EXITS,
        SECTION_FAILURES,
        SECTION_TIME,
    )

    out_dir = tmp_path / "results"
    assert main(["sweep", str(_export_zip(tmp_path)), "--seeds", "2", "--out", str(out_dir)]) == 0
    report_path = tmp_path / "report.html"
    rc = main(["report", str(out_dir), "--out", str(report_path)])
    assert rc == 0
    assert _last_json_line(capsys.readouterr().out)["report"] == str(report_path)
    html = report_path.read_text()
    for heading in (SECTION_TIME, SECTION_EXITS, SECTION_ARRIVAL, SECTION_DENSITY, SECTION_FAILURES):
        assert f"<h2>{heading}</h2>" in html
    assert "data:image/png;base64," in html
    assert "jps-exits_0" in html


def test_cli_report_missing_sweep_json(tmp_path, capsys):
    pytest.importorskip("matplotlib")
    rc = main(["report", str(tmp_path)])
    assert rc == 2
    assert "sweep.json" in capsys.readouterr().err


FOUR_START_AREAS = pathlib.Path(__file__).parent / "fixtures" / "four_start_areas"


def test_cli_sweep_and_report_with_one_failing_seed(tmp_path, capsys):
    """Scale 2 passes the dry run for the base seed (420) but seed 2 cannot
    place 20 agents in 'jps-distributions_2': the sweep still completes,
    sweep.json is written and the report lists the failure."""
    pytest.importorskip("jupedsim")
    pytest.importorskip("matplotlib")
    from jupedsim_scenarios import SweepResult
    from jupedsim_scenarios.report import SECTION_FAILURES, SECTION_TIME

    out_dir = tmp_path / "results"
    rc = main(
        ["sweep", str(FOUR_START_AREAS), "--seeds", "3", "--scale", "2", "--workers", "2", "--out", str(out_dir)]
    )
    out = capsys.readouterr()
    assert rc == 0, out.err
    assert "Traceback" not in out.err
    summary = _last_json_line(out.out)
    assert summary["n_trials"] == 3
    assert summary["n_failed"] == 1
    sweep = SweepResult.load(out_dir / "sweep.json")
    failed = [t for t in sweep.trials if not t.result.success]
    assert [t.seed for t in failed] == [2]
    assert "Only 17 of 20" in failed[0].result.metrics["message"]

    report_path = tmp_path / "report.html"
    assert main(["report", str(out_dir), "--out", str(report_path)]) == 0
    html = report_path.read_text()
    assert f"<h2>{SECTION_TIME}</h2>" in html
    assert "mean over 2 seeds" in html
    assert f"<h2>{SECTION_FAILURES}</h2>" in html
    assert "Only 17 of 20" in html


def test_cli_sweep_all_failed_exits_1_and_report_degrades(tmp_path, capsys):
    """Only seed 2, which cannot place the scaled count: every trial fails,
    the exit code is 1, sweep.json exists and the report renders without
    a single successful trial."""
    pytest.importorskip("jupedsim")
    pytest.importorskip("matplotlib")
    from jupedsim_scenarios.report import SECTION_FAILURES

    out_dir = tmp_path / "results"
    rc = main(
        [
            "sweep", str(FOUR_START_AREAS), "--seed-start", "2", "--seed-end", "2",
            "--scale", "2", "--out", str(out_dir),
        ]
    )
    out = capsys.readouterr()
    assert rc == 1
    assert "Traceback" not in out.err
    summary = _last_json_line(out.out)
    assert (summary["n_trials"], summary["n_failed"]) == (1, 1)
    assert (out_dir / "sweep.json").exists()

    report_path = tmp_path / "report.html"
    assert main(["report", str(out_dir), "--out", str(report_path)]) == 0
    html = report_path.read_text()
    assert f"<h2>{SECTION_FAILURES}</h2>" in html
    assert "No trial completed" in html
    assert "Only 17 of 20" in html


_NOISY_SWEEP = """
import logging, sys
logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
from jupedsim_scenarios.cli import main
sys.exit(main(sys.argv[1:]))
"""


@pytest.mark.parametrize(("verbose", "workers"), [(False, 1), (False, 2), (True, 1)])
def test_cli_sweep_hides_library_info_unless_verbose(tmp_path, verbose, workers):
    """A root INFO handler (as PedPy 1.5 installs on import) must not turn
    every trial into a parameter dump; --verbose opts back in. The handler
    here lives only in the parent, so the verbose case runs sequentially."""
    import subprocess
    import sys

    fixture = pathlib.Path(__file__).parent / "golden" / "fixtures" / "collisionfreespeedmodel"
    argv = ["sweep", str(fixture), "--seeds", "2", "--workers", str(workers), "--out", str(tmp_path / "out")]
    if verbose:
        argv.insert(0, "--verbose")
    proc = subprocess.run([sys.executable, "-c", _NOISY_SWEEP, *argv], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    combined = proc.stdout + proc.stderr
    assert ("INFO - " in combined) is verbose
