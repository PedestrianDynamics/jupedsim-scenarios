"""End-to-end smoke test: run the corridor fixture, assert evacuation."""

from __future__ import annotations

import pathlib

import pytest

from jupedsim_scenarios import ScenarioResult, run_scenario


def test_run_scenario_corridor_evacuates(corridor_scenario):
    result: ScenarioResult = run_scenario(corridor_scenario, seed=42)
    try:
        assert result.success, result.metrics.get("message")
        assert result.metrics["agents_evacuated"] > 0
        assert pathlib.Path(result.sqlite_file).exists()
    finally:
        result.cleanup()


def test_every_nth_frame_param_changes_reported_rate(corridor_scenario):
    # Stride 1 → frame rate equals 1/dt. Stride 20 → half of the
    # default. The hardcoded 10.0 fps default is no longer baked in.
    fast = run_scenario(corridor_scenario, seed=42, every_nth_frame=1)
    try:
        assert fast.frame_rate == pytest.approx(1.0 / fast.dt)
    finally:
        fast.cleanup()

    coarse = run_scenario(corridor_scenario, seed=42, every_nth_frame=20)
    try:
        assert coarse.frame_rate == pytest.approx(1.0 / (coarse.dt * 20))
    finally:
        coarse.cleanup()


def test_run_scenario_writes_to_explicit_output_path(corridor_scenario, tmp_path):
    target = tmp_path / "nested" / "trajectory.sqlite"
    result = run_scenario(corridor_scenario, seed=42, output_path=target)
    try:
        assert pathlib.Path(result.sqlite_file).resolve() == target.resolve()
        assert target.exists()
    finally:
        result.cleanup()
    # cleanup() removes the file even though it lives under tmp_path.
    assert not target.exists()


def test_run_scenario_rejects_bad_params(corridor_scenario):
    with pytest.raises(ValueError, match="every_nth_frame"):
        run_scenario(corridor_scenario, every_nth_frame=0)
    with pytest.raises(ValueError, match="dt"):
        run_scenario(corridor_scenario, dt=0)


def test_frame_rate_and_dt_come_from_live_simulation(corridor_scenario):
    # dt is jupedsim's default (0.01s) and the writer stride is 10 →
    # 10 fps. The properties used to silently fall back to those numbers
    # even if the simulator told us something different; they now read
    # the real values, so a future change to either input will surface
    # here instead of being papered over.
    result: ScenarioResult = run_scenario(corridor_scenario, seed=42)
    try:
        assert result.dt == 0.01
        assert result.frame_rate == 10.0
    finally:
        result.cleanup()
