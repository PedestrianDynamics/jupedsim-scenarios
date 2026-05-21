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
