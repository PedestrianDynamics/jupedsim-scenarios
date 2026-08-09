"""The fallback path must pick its first hop's target with the same rule
as every later hop.

Both fallback spawn sites used to assign the first target with a raw
``_random_point_in_polygon(polygon, rng)`` (min_clearance 0.2), while the
runtime picks every subsequent hop through the transit/waiting rule —
centroid for a transit stage. So the same checkpoint was aimed at from a
random interior point when it happened to be first in the chain and at the
centroid on any later visit, which made routing measurements depend on
chain position. The journeys_v2 path already used
``_pick_initial_stage_target``; both fallback sites now do too (#76).

Covered here via ``_initialize_with_fallback`` (no ``journeys_v2`` at all).
The sibling site in ``_add_agents`` intentionally does not chain: its first
hop is always the exit (#79) — same picker, nothing checkpoint-shaped to
assert on.
"""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

CHECKPOINT_ID = "jps-checkpoints_0"
CHECKPOINT_COORDS = [[9, 2], [11, 2], [11, 3], [9, 3], [9, 2]]
CHECKPOINT_CENTROID = (10.0, 2.5)


def _scenario_with_checkpoint():
    """Corridor fixture plus one speed-factor checkpoint and no journeys, so
    ``_build_fallback_checkpoint_chain`` makes the checkpoint the first hop
    for every agent.

    The checkpoint has to carry behavior — an inert one is no longer chained
    (#76). ``speed_factor`` keeps ``waiting_time`` at 0, so the stage is still
    transit and the expected target is still the centroid."""
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import Scenario

    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    data["checkpoints"] = {
        CHECKPOINT_ID: {
            "type": "polygon",
            "coordinates": CHECKPOINT_COORDS,
            "waiting_time": 0,
            "speed_factor": 0.5,
            "enable_throughput_throttling": False,
        }
    }

    data.pop("journeys_v2", None)
    data["distributions"]["jps-distributions_0"].pop("journey_weights", None)

    sim_params = data["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=data,
        walkable_area_wkt=data["walkable_area_wkt"],
        model_type=sim_params["model_type"],
        seed=data["seed"],
        sim_params=dict(sim_params),
        source_path=str(FIXTURES / "corridor_simple.json"),
    )


def test_first_hop_target_is_the_transit_centroid():
    from jupedsim_scenarios import ScenarioRunner

    scenario = _scenario_with_checkpoint()
    with ScenarioRunner(scenario, seed=42) as runner:
        wait_info = dict(runner._spawning_info["agent_wait_info"])

    chained = {
        agent_id: info
        for agent_id, info in wait_info.items()
        if info.get("current_target_stage") == CHECKPOINT_ID
    }
    assert chained, (
        "no agent was chained through the checkpoint; the test no longer "
        f"exercises the fallback chain (wait info: {wait_info})"
    )

    for agent_id, info in chained.items():
        target = info["target"]
        assert target == pytest.approx(CHECKPOINT_CENTROID), (
            f"agent {agent_id} aims at {target}, not the checkpoint centroid; "
            "the fallback first hop bypassed _pick_initial_stage_target again"
        )
