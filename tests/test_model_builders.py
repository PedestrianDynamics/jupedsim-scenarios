"""Every registered model builder must construct against the installed jupedsim.

CollisionFreeSpeedModelV2 crashed with TypeError on every run: the builder
passed strength/range_neighbor_repulsion, but the upstream V2 operational
model takes no constructor args — those params are per-agent
(CollisionFreeSpeedModelV2AgentParameters, populated in simulation_init).
Constructing each builder with defaults and with all known model-param
keys pins the registry against upstream signature drift.
"""

from __future__ import annotations

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios import Scenario, run_scenario
from jupedsim_scenarios.runner import _MODEL_BUILDERS, _MODEL_PARAM_KEYS, _build_model

_FULL_PARAMS = dict.fromkeys(_MODEL_PARAM_KEYS, 0.5)


@pytest.mark.parametrize("model_type", sorted(_MODEL_BUILDERS))
def test_builder_constructs_with_defaults(model_type):
    assert _build_model(model_type, {}) is not None


@pytest.mark.parametrize("model_type", sorted(_MODEL_BUILDERS))
def test_builder_constructs_with_all_known_param_keys(model_type):
    # Builders read from sim_params by allow-listed key; unknown-to-them
    # keys must be ignored, known ones accepted by the upstream constructor.
    assert _build_model(model_type, dict(_FULL_PARAMS)) is not None


def test_v2_scenario_runs_end_to_end():
    s = Scenario(
        raw={},
        walkable_area_wkt="POLYGON((0 0, 12 0, 12 4, 0 4, 0 0))",
        model_type="CollisionFreeSpeedModelV2",
        seed=3,
        sim_params={"max_simulation_time": 60},
    )
    s.add_distribution([(0.5, 0.5), (3, 0.5), (3, 3.5), (0.5, 3.5)], number=6)
    s.add_exit([(11.5, 1), (12, 1), (12, 3), (11.5, 3)])
    result = run_scenario(s, seed=3)
    assert result.success
    result.cleanup()


def test_v2_agent_time_gap_comes_from_model_params():
    # V2's time gap T was hard-coded to 1.0, so a user-set value never
    # reached the agents.
    from types import SimpleNamespace

    from jupedsim_scenarios.simulation_init import create_agent_parameters

    def time_gap(global_params):
        return create_agent_parameters(
            "CollisionFreeSpeedModelV2", (0.0, 0.0), {}, global_params
        ).time_gap

    assert time_gap(SimpleNamespace(time_gap=1.7)) == pytest.approx(1.7)
    assert time_gap(SimpleNamespace()) == pytest.approx(1.0)
    assert time_gap(None) == pytest.approx(1.0)


def _agent(model_type, global_params):
    from jupedsim_scenarios.simulation_init import create_agent_parameters

    return create_agent_parameters(model_type, (0.0, 0.0), {}, global_params)


def test_v3_agent_params_come_from_v3_keys():
    from types import SimpleNamespace

    g = SimpleNamespace(
        v3_time_gap=1.5,
        v3_strength_neighbor_repulsion=3.0,
        v3_range_neighbor_repulsion=0.2,
        v3_strength_geometry_repulsion=4.0,
        v3_range_geometry_repulsion=0.05,
        v3_range_x_scale=15.0,
        v3_range_y_scale=6.0,
        v3_theta_max_upper_bound=1.2,
        v3_agent_buffer=0.1,
    )
    agent = _agent("CollisionFreeSpeedModelV3", g)
    assert agent.time_gap == pytest.approx(1.5)
    assert agent.strength_neighbor_repulsion == pytest.approx(3.0)
    assert agent.range_neighbor_repulsion == pytest.approx(0.2)
    assert agent.strength_geometry_repulsion == pytest.approx(4.0)
    assert agent.range_geometry_repulsion == pytest.approx(0.05)
    assert agent.range_x_scale == pytest.approx(15.0)
    assert agent.range_y_scale == pytest.approx(6.0)
    assert agent.theta_max_upper_bound == pytest.approx(1.2)
    assert agent.agent_buffer == pytest.approx(0.1)


def test_v3_ignores_shared_v2_keys():
    from types import SimpleNamespace

    g = SimpleNamespace(time_gap=2.5, strength_neighbor_repulsion=2.6)
    agent = _agent("CollisionFreeSpeedModelV3", g)
    assert agent.time_gap == pytest.approx(1.0)
    assert agent.strength_neighbor_repulsion == pytest.approx(8.0)


def test_v1_time_gap_from_csm_time_gap():
    from types import SimpleNamespace

    model = "CollisionFreeSpeedModel"
    assert _agent(model, SimpleNamespace(csm_time_gap=1.8)).time_gap == pytest.approx(1.8)
    assert _agent(model, SimpleNamespace(time_gap=2.5)).time_gap == pytest.approx(1.0)
    assert _agent(model, None).time_gap == pytest.approx(1.0)


def test_v2_unaffected_by_v3_and_avm_keys():
    from types import SimpleNamespace

    g = SimpleNamespace(
        time_gap=1.4,
        strength_neighbor_repulsion=2.6,
        range_neighbor_repulsion=0.1,
        v3_time_gap=3.0,
        avm_time_gap=3.0,
    )
    agent = _agent("CollisionFreeSpeedModelV2", g)
    assert agent.time_gap == pytest.approx(1.4)
    assert agent.strength_neighbor_repulsion == pytest.approx(2.6)


def test_set_model_params_accepts_csm_and_v3_keys():
    s = Scenario(
        raw={"distributions": {"d0": {"parameters": {}}}},
        walkable_area_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        model_type="CollisionFreeSpeedModelV3",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )
    s.set_model_params(v3_agent_buffer=0.2, csm_time_gap=1.1)
    assert s.sim_params["v3_agent_buffer"] == 0.2
    assert s.sim_params["csm_time_gap"] == 1.1


def test_avm_agent_params_come_from_avm_keys():
    from types import SimpleNamespace

    g = SimpleNamespace(
        avm_time_gap=1.3,
        avm_strength_neighbor_repulsion=6.0,
        avm_range_neighbor_repulsion=0.3,
        avm_wall_buffer_distance=0.25,
    )
    agent = _agent("AnticipationVelocityModel", g)
    assert agent.time_gap == pytest.approx(1.3)
    assert agent.strength_neighbor_repulsion == pytest.approx(6.0)
    assert agent.range_neighbor_repulsion == pytest.approx(0.3)
    assert agent.wall_buffer_distance == pytest.approx(0.25)


def test_avm_jupedsim_names_beat_app_names():
    from types import SimpleNamespace

    g = SimpleNamespace(T=1.0, s0=0.5, anticipation_time=2.0, reaction_time=0.8)
    agent = _agent("AnticipationVelocityModel", g)
    assert agent.anticipation_time == pytest.approx(2.0)
    assert agent.reaction_time == pytest.approx(0.8)


def test_avm_app_names_still_work():
    from types import SimpleNamespace

    agent = _agent("AnticipationVelocityModel", SimpleNamespace(T=1.5, s0=0.4))
    assert agent.anticipation_time == pytest.approx(1.5)
    assert agent.reaction_time == pytest.approx(0.4)


def test_avm_defaults_when_unset():
    from types import SimpleNamespace

    for g in (None, SimpleNamespace()):
        agent = _agent("AnticipationVelocityModel", g)
        assert agent.time_gap == pytest.approx(1.06)
        assert agent.strength_neighbor_repulsion == pytest.approx(8.0)
        assert agent.range_neighbor_repulsion == pytest.approx(0.1)
        assert agent.wall_buffer_distance == pytest.approx(0.1)
        assert agent.anticipation_time == pytest.approx(1.0)
        assert agent.reaction_time == pytest.approx(0.3)


def test_set_model_params_anticipation_time_takes_effect():
    from types import SimpleNamespace

    s = Scenario(
        raw={"distributions": {"d0": {"parameters": {}}}},
        walkable_area_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        model_type="AnticipationVelocityModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )
    s.set_model_params(anticipation_time=2.0, reaction_time=0.7)
    agent = _agent("AnticipationVelocityModel", SimpleNamespace(**s.sim_params))
    assert agent.anticipation_time == pytest.approx(2.0)
    assert agent.reaction_time == pytest.approx(0.7)
