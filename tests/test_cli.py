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
