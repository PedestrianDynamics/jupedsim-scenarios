"""Regression test for issue #15.

Before the fix in `direct_steering_runtime.check_stage_reached`, the
exit-arrival despawn required the agent's center to be inside the exit
polygon. For a narrow exit (5 cm wide here), the routing's arrival
waypoint can land just outside, so the agent stalls a few cm short and
the simulation runs until `max_simulation_time`.

The fix accepts body-intersection (disk of `agent_radius` overlapping the
polygon) as "exit reached", which matches the natural reading of "the
agent reached the exit".
"""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def narrow_exit_scenario():
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import Scenario

    data = json.loads((FIXTURES / "issue_15_narrow_exit.json").read_text())
    sim_params = data["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=data,
        walkable_area_wkt=data["walkable_area_wkt"],
        model_type=sim_params["model_type"],
        seed=data["seed"],
        sim_params=dict(sim_params),
        source_path=str(FIXTURES / "issue_15_narrow_exit.json"),
    )


def test_narrow_exit_agent_despawns(narrow_exit_scenario):
    """Single agent through a 5cm-wide exit must evacuate well before
    `max_simulation_time = 60s`. Pre-fix this hit the cap at 60.0s."""
    from jupedsim_scenarios import run_scenario

    result = run_scenario(narrow_exit_scenario, seed=42)
    try:
        assert result.success, result.metrics.get("message")
        assert result.metrics["agents_evacuated"] == 1, (
            f"expected the single agent to evacuate; "
            f"metrics={result.metrics}"
        )
        assert result.evacuation_time < 30.0, (
            f"evacuation_time={result.evacuation_time:.2f}s suggests the "
            "despawn never fired (pre-fix this pinned at max_simulation_time=60s)"
        )
    finally:
        result.cleanup()
