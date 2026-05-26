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
