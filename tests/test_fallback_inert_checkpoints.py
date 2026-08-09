"""Inert checkpoints must not become mandatory waypoints (#76).

A scenario with no ``journeys_v2`` used to route the whole population through
every declared checkpoint, in JSON insertion order, before the nearest exit.
Drawing a stage in the editor and not wiring it into a journey therefore
rewrote all routing silently: a 0.49 m circle serialises the crowd and the
chain can cross the geometry several times.

The chain now only carries checkpoints that do something —
``waiting_time > 0``, ``speed_factor != 1``, or effective throttling
(``enable_throughput_throttling`` with ``max_throughput > 0``). The #8 behavior
that the chain exists for is retained and pinned below.

These are end-to-end assertions: the unit tests over the builder in
``test_fallback_checkpoint_chain.py`` passed throughout the bug, because the
chain was always built exactly as designed.
"""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from jupedsim_scenarios.simulation_init import _checkpoint_carries_behavior

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

CP_A = "jps-checkpoints_0"
CP_B = "jps-checkpoints_1"
CP_C = "jps-checkpoints_2"


def _inert_checkpoint(coords):
    return {
        "type": "polygon",
        "coordinates": coords,
        "waiting_time": 0,
        "speed_factor": 1,
        "enable_throughput_throttling": False,
    }


def _fallback_scenario(**overrides):
    """Corridor fixture stripped of its journey, so every agent takes the
    fallback (no ``journeys_v2``) path."""
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import Scenario

    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    data.pop("journeys_v2", None)
    data["distributions"]["jps-distributions_0"].pop("journey_weights", None)
    data.update(copy.deepcopy(overrides))

    sim_params = data["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=data,
        walkable_area_wkt=data["walkable_area_wkt"],
        model_type=sim_params["model_type"],
        seed=data["seed"],
        sim_params=dict(sim_params),
        source_path=str(FIXTURES / "corridor_simple.json"),
    )


def _wait_info(scenario):
    from jupedsim_scenarios import ScenarioRunner

    with ScenarioRunner(scenario, seed=42) as runner:
        return dict(runner._spawning_info["agent_wait_info"])


# --- the predicate ----------------------------------------------------------


@pytest.mark.parametrize(
    "info,expected",
    [
        ({"waiting_time": 0.0, "speed_factor": 1.0}, False),
        ({"waiting_time": 5.0, "speed_factor": 1.0}, True),
        ({"waiting_time": 0.0, "speed_factor": 0.5}, True),
        # Throttling with no rate is a runtime no-op, so it is inert.
        (
            {
                "waiting_time": 0.0,
                "speed_factor": 1.0,
                "enable_throughput_throttling": True,
                "max_throughput": 0.0,
            },
            False,
        ),
        (
            {
                "waiting_time": 0.0,
                "speed_factor": 1.0,
                "enable_throughput_throttling": True,
                "max_throughput": 2.0,
            },
            True,
        ),
        # A bare stage dict (no keys at all) is inert, not an error.
        ({}, False),
    ],
)
def test_carries_behavior_predicate(info, expected):
    assert _checkpoint_carries_behavior(info) is expected


# --- routing ----------------------------------------------------------------


def test_inert_checkpoint_is_not_a_waypoint():
    scenario = _fallback_scenario(
        checkpoints={CP_A: _inert_checkpoint([[9, 2], [11, 2], [11, 3], [9, 3], [9, 2]])}
    )
    for agent_id, info in _wait_info(scenario).items():
        assert info["current_target_stage"] == "jps-exits_0", (
            f"agent {agent_id} was routed through the inert checkpoint "
            f"{info['current_target_stage']}"
        )
        assert info["path_choices"] == {}


def test_waiting_checkpoint_is_still_chained():
    """#8: the chain exists so fallback agents honor checkpoint waiting_time."""
    scenario = _fallback_scenario(
        checkpoints={
            CP_A: {
                "type": "polygon",
                "coordinates": [[9, 2], [11, 2], [11, 3], [9, 3], [9, 2]],
                "waiting_time": 3,
                "speed_factor": 1,
                "enable_throughput_throttling": False,
            }
        }
    )
    for agent_id, info in _wait_info(scenario).items():
        assert info["current_target_stage"] == CP_A, (
            f"agent {agent_id} skipped the waiting checkpoint — #8 regressed"
        )
        assert info["path_choices"] == {CP_A: [("jps-exits_0", 100.0)]}
        assert info["stage_configs"][CP_A]["waiting_time"] == pytest.approx(3.0)


def test_inert_checkpoints_dropped_from_a_mixed_chain():
    """Only behavior-carrying stages survive, and JSON insertion order holds.

    Two survivors, with the inert one inserted between them, so the order
    assertion has something to fail on — the declared semantics are a single
    chain in scenario JSON order, unaffected by spawn position.
    """
    scenario = _fallback_scenario(
        checkpoints={
            CP_B: {
                "type": "polygon",
                "coordinates": [[4, 2], [5, 2], [5, 3], [4, 3], [4, 2]],
                "waiting_time": 2,
                "speed_factor": 1,
                "enable_throughput_throttling": False,
            },
            CP_A: _inert_checkpoint([[9, 2], [11, 2], [11, 3], [9, 3], [9, 2]]),
            CP_C: {
                "type": "polygon",
                "coordinates": [[14, 2], [15, 2], [15, 3], [14, 3], [14, 2]],
                "waiting_time": 0,
                "speed_factor": 0.5,
                "enable_throughput_throttling": False,
            },
        }
    )
    for info in _wait_info(scenario).values():
        assert info["current_target_stage"] == CP_B
        assert info["path_choices"] == {
            CP_B: [(CP_C, 100.0)],
            CP_C: [("jps-exits_0", 100.0)],
        }
        # Dropped from routing, but still present as a runtime stage config.
        assert CP_A in info["stage_configs"]


# --- evacuation -------------------------------------------------------------


def test_fallback_scenario_with_inert_checkpoints_evacuates():
    """End-to-end: the assertion the builder unit tests could never make."""
    from jupedsim_scenarios import ScenarioRunner

    scenario = _fallback_scenario(
        checkpoints={
            CP_A: _inert_checkpoint([[5, 2], [6, 2], [6, 3], [5, 3], [5, 2]]),
            CP_B: _inert_checkpoint([[14, 2], [15, 2], [15, 3], [14, 3], [14, 2]]),
        }
    )
    with ScenarioRunner(scenario, seed=42) as runner:
        runner.run_until()
        result = runner.result()

    assert result.metrics["all_evacuated"], (
        f"{result.metrics['agents_remaining']} agents left at "
        f"{result.metrics['evacuation_time']}s: {result.metrics['message']}"
    )


def test_multi_exit_fallback_feeds_both_exits():
    """Each agent still leaves by the exit nearest its own spawn point.

    Bracketing the corridor with an exit at each end and spawning in both
    ends must use both. This is the property the inert chain destroyed: its
    last hop was pinned to the exit nearest the spawn, but every agent first
    walked the whole chain, so they all arrived from the same place.
    """
    from jupedsim_scenarios import ScenarioRunner

    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    exits = {
        "jps-exits_0": {
            "type": "polygon",
            "coordinates": [[18, 0], [20, 0], [20, 5], [18, 5], [18, 0]],
            "enable_throughput_throttling": False,
            "max_throughput": 0,
        },
        "jps-exits_1": {
            "type": "polygon",
            "coordinates": [[0, 0], [2, 0], [2, 5], [0, 5], [0, 0]],
            "enable_throughput_throttling": False,
            "max_throughput": 0,
        },
    }
    distributions = {
        "jps-distributions_0": copy.deepcopy(data["distributions"]["jps-distributions_0"]),
        "jps-distributions_1": copy.deepcopy(data["distributions"]["jps-distributions_0"]),
    }
    distributions["jps-distributions_0"]["coordinates"] = [
        [3, 1],
        [6, 1],
        [6, 4],
        [3, 4],
        [3, 1],
    ]
    distributions["jps-distributions_1"]["coordinates"] = [
        [14, 1],
        [17, 1],
        [17, 4],
        [14, 4],
        [14, 1],
    ]

    scenario = _fallback_scenario(
        exits=exits,
        distributions=distributions,
        checkpoints={CP_A: _inert_checkpoint([[9, 2], [11, 2], [11, 3], [9, 3], [9, 2]])},
    )

    targets = {info["current_target_stage"] for info in _wait_info(scenario).values()}
    assert targets == {"jps-exits_0", "jps-exits_1"}, (
        f"agents only head for {targets}; the fallback path is not using both exits"
    )

    with ScenarioRunner(scenario, seed=42) as runner:
        runner.run_until()
        assert runner.result().metrics["all_evacuated"]
