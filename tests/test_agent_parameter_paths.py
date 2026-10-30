"""Initial placement and flow spawning resolve the same agent parameters."""

from __future__ import annotations

import copy
import pathlib

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios import ScenarioRunner, load_scenario

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
V2 = "CollisionFreeSpeedModelV2"
OVERRIDES = {"strength_neighbor_repulsion": 3.7, "time_gap": 0.45}


def _scenario(journeys=True, variants=True):
    scenario = load_scenario(str(FIXTURES / "corridor_simple.json"))
    if not journeys:
        scenario.raw["journeys_v2"] = []
        for dist in scenario.raw["distributions"].values():
            dist.pop("journey_weights", None)
    scenario.model_type = V2
    scenario.max_simulation_time = 10
    dists = scenario.raw["distributions"]
    placed = dists["jps-distributions_0"]
    placed["coordinates"] = [[0, 0], [4, 0], [4, 2.5], [0, 2.5], [0, 0]]
    placed["parameters"]["number"] = 3
    flow = copy.deepcopy(placed)
    flow["coordinates"] = [[0, 2.5], [4, 2.5], [4, 5], [0, 5], [0, 2.5]]
    flow["parameters"].update(
        {"use_flow_spawning": True, "flow_start_time": 0, "flow_end_time": 2}
    )
    dists["jps-distributions_1"] = flow
    if not variants:
        # The placed area has no journey variants (nearest exit) while the
        # flow area keeps its journey, so the journeys_v2 path still runs.
        placed.pop("journey_weights", None)
    scenario.set_agent_params(0, agent_parameter_overrides={V2: OVERRIDES})
    scenario.set_agent_params(1, agent_parameter_overrides={V2: OVERRIDES})
    return scenario


@pytest.mark.parametrize(
    ("journeys", "variants"), [(True, True), (True, False), (False, True)]
)
def test_placement_and_flow_resolve_identically(journeys, variants):
    with ScenarioRunner(_scenario(journeys, variants), seed=42) as runner:
        placed = {a.id for a in runner.simulation.agents()}
        runner.run_until(4.0)
        spawned = {a.id for a in runner.simulation.agents()} - placed
        assert placed
        # Flow spawning is asserted on the journeys_v2 path only.
        assert spawned or not journeys
        for agent_id in placed | spawned:
            model = runner.simulation.agent(agent_id).model
            assert model.strength_neighbor_repulsion == pytest.approx(3.7)
            assert model.time_gap == pytest.approx(0.45)
