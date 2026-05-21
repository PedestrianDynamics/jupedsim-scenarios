"""Shared fixtures for the test suite."""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def corridor_scenario():
    """A `Scenario` built from the corridor_simple.json fixture.

    Imported lazily so the suite still collects when jupedsim isn't
    installed — individual tests that need the simulation gate with
    `pytest.importorskip("jupedsim")`.
    """
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import Scenario

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
