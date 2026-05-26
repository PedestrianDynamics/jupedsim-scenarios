"""End-to-end smoke test: run the corridor fixture, assert evacuation."""

from __future__ import annotations

import pathlib

from jupedsim_scenarios import ScenarioResult, run_scenario


def test_run_scenario_corridor_evacuates(corridor_scenario):
    result: ScenarioResult = run_scenario(corridor_scenario, seed=42)
    try:
        assert result.success, result.metrics.get("message")
        assert result.metrics["agents_evacuated"] > 0
        assert pathlib.Path(result.sqlite_file).exists()
    finally:
        result.cleanup()


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
