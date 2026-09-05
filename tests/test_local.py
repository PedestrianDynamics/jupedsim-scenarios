"""Tests for run_local, the library form of ``jps-scenarios sweep``."""

from __future__ import annotations

import json
import pathlib

import pytest

GOLDEN = pathlib.Path(__file__).parent / "golden" / "fixtures" / "collisionfreespeedmodel"

META_KEYS = {
    "scenario_source",
    "scenario_json",
    "scale",
    "scale_mode",
    "seeds",
    "dt",
    "every_nth_frame",
    "wall_clock_s",
    "library_version",
}


def test_run_local_is_exported():
    import jupedsim_scenarios

    assert "run_local" in jupedsim_scenarios.__all__
    assert jupedsim_scenarios.run_local is jupedsim_scenarios.local.run_local


def test_run_local_writes_layout_and_reports_progress(tmp_path):
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import SweepResult, run_local

    out_dir = tmp_path / "results"
    calls: list[tuple[int, int, dict]] = []

    sweep = run_local(
        GOLDEN,
        out_dir=out_dir,
        seeds=2,
        workers=1,
        progress=lambda done, total, payload: calls.append((done, total, dict(payload))),
    )

    assert [(d, t) for d, t, _ in calls] == [(1, 2), (2, 2)]
    assert [p["seed"] for _, _, p in calls] == [0, 1]
    assert len(sweep) == 2
    for t in sweep.trials:
        assert t.result.success, t.result.metrics.get("message")
    assert sorted(p.name for p in out_dir.glob("trial_*.sqlite")) == [
        "trial_00000.sqlite",
        "trial_00001.sqlite",
    ]
    assert (out_dir / "scenario.json").exists()

    saved = json.loads((out_dir / "sweep.json").read_text())
    assert META_KEYS <= set(saved["meta"])
    assert saved["meta"]["seeds"] == [0, 1]
    assert saved["meta"]["scale"] == 1.0
    assert saved["meta"]["scenario_source"] == str(GOLDEN)
    assert sweep.meta == saved["meta"]
    assert len(SweepResult.load(out_dir / "sweep.json")) == 2
