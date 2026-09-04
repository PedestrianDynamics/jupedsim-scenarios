"""``Scenario.scale_agents``: count mode refuses at the capacity boundary,
flow mode keeps the spawn rate, and each mode refuses the wrong kind of
distribution."""

from __future__ import annotations

import copy

import pytest

from jupedsim_scenarios import (
    PRACTICAL_PACKING_FACTOR,
    CapacityError,
    max_agents_for_distribution,
    scale_agents,
)

DIST = "jps-distributions_0"


def _params(scenario):
    return scenario.distributions[DIST]["parameters"]


def test_max_agents_matches_app_rule(corridor_scenario):
    # 4 x 5 m start area, radius 0.15: floor(20 / (pi * 0.0225) * 0.5) = 141
    assert PRACTICAL_PACKING_FACTOR == 0.5
    assert max_agents_for_distribution(corridor_scenario, DIST) == 141


def test_max_agents_subtracts_obstacles(corridor_scenario):
    corridor_scenario.walkable_area_wkt = (
        "POLYGON ((0 0, 20 0, 20 5, 0 5, 0 0), (1 1, 3 1, 3 3, 1 3, 1 1))"
    )
    # 20 m2 minus a 4 m2 hole
    assert max_agents_for_distribution(corridor_scenario, DIST) == 113


def test_count_mode_passes_at_capacity(corridor_scenario):
    limit = max_agents_for_distribution(corridor_scenario, DIST)
    _params(corridor_scenario)["number"] = 1
    corridor_scenario.scale_agents(limit)
    assert _params(corridor_scenario)["number"] == limit


def test_count_mode_refuses_one_over_capacity_and_leaves_scenario_untouched(corridor_scenario):
    limit = max_agents_for_distribution(corridor_scenario, DIST)
    _params(corridor_scenario)["number"] = 1
    before = copy.deepcopy(corridor_scenario.raw)
    with pytest.raises(CapacityError, match="mode='flow'") as exc:
        corridor_scenario.scale_agents(limit + 1)
    assert DIST in str(exc.value)
    assert f"requested {limit + 1}, max {limit}" in str(exc.value)
    assert corridor_scenario.raw == before
    assert isinstance(exc.value, ValueError)


def test_count_mode_rounds_and_scales_flow_numbers(corridor_scenario):
    params = _params(corridor_scenario)
    params["number"] = 10
    params["initial_number"] = 3
    corridor_scenario.scale_agents(2.5)
    assert params["number"] == 25
    assert params["initial_number"] == 8


def test_scale_agents_function_alias(corridor_scenario):
    scale_agents(corridor_scenario, 2)
    assert _params(corridor_scenario)["number"] == 20


def test_factor_must_be_positive(corridor_scenario):
    with pytest.raises(ValueError, match="factor"):
        corridor_scenario.scale_agents(0)


def test_flow_mode_refuses_static_distribution(corridor_scenario):
    with pytest.raises(ValueError, match="flow spawning"):
        corridor_scenario.scale_agents(2, mode="flow")


def test_flow_mode_keeps_rate(corridor_scenario):
    params = _params(corridor_scenario)
    params.update(
        {"use_flow_spawning": True, "flow_start_time": 2, "flow_end_time": 12, "number": 20}
    )
    corridor_scenario.scale_agents(3, mode="flow")
    assert params["number"] == 60
    assert params["flow_start_time"] == 2
    assert params["flow_end_time"] == 32
    rate = params["number"] / (params["flow_end_time"] - params["flow_start_time"])
    assert rate == pytest.approx(2.0)


def test_flow_mode_stretches_schedule_entries(corridor_scenario):
    corridor_scenario.set_flow_schedule(
        DIST,
        [
            {"flow_start_time": 0, "flow_end_time": 10, "number": 10},
            {"flow_start_time": 10, "flow_end_time": 20, "number": 20},
        ],
    )
    corridor_scenario.scale_agents(2, mode="flow")
    schedule = _params(corridor_scenario)["flow_schedule"]
    assert [e["number"] for e in schedule] == [20, 40]
    assert [(e["flow_start_time"], e["flow_end_time"]) for e in schedule] == [(0, 20), (20, 40)]
