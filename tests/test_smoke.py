"""End-to-end smoke test: load the corridor fixture, run, assert results.

If `jupedsim` is not importable in the CI environment, the suite skips —
this lets the lint/build jobs still run on platforms where jupedsim isn't
yet available as a wheel.
"""

from __future__ import annotations

import json
import pathlib

import pytest

jps = pytest.importorskip("jupedsim")

from jupedsim_scenarios import Scenario, ScenarioResult, run_scenario  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _load_corridor() -> Scenario:
    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    sim_params = (
        data.get("config", {}).get("simulation_settings", {}).get("simulationParams", {})
    )
    sim_params.setdefault("max_simulation_time", 60)
    return Scenario(
        raw=data,
        walkable_area_wkt=data["walkable_area_wkt"],
        model_type=sim_params.get("model_type", "CollisionFreeSpeedModel"),
        seed=data.get("seed", 42),
        sim_params=dict(sim_params),
        source_path=str(FIXTURES / "corridor_simple.json"),
    )


def test_run_scenario_corridor_evacuates():
    scenario = _load_corridor()
    result: ScenarioResult = run_scenario(scenario, seed=42)
    try:
        assert result.success, result.metrics.get("message")
        assert result.metrics["agents_evacuated"] > 0
        assert pathlib.Path(result.sqlite_file).exists()
    finally:
        result.cleanup()
