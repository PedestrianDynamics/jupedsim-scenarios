"""Script API for per-area agent parameter overrides and the sweep precedence warning."""

from __future__ import annotations

import logging
import pathlib
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("jupedsim")

import jupedsim as jps

from jupedsim_scenarios import (
    AgentParameterError,
    load_scenario,
    run_scenario,
    run_sweep,
    run_sweep_from_factory,
)
from jupedsim_scenarios.agent_parameters import validate_agent_parameters
from jupedsim_scenarios.simulation_init import create_agent_parameters

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
V2 = "CollisionFreeSpeedModelV2"
GCFM = "GeneralizedCentrifugalForceModel"
KEY = "agent_parameter_overrides"
WARNING_TEXT = (
    "time_gap changes the default of time_gap; spawn areas that override it "
    "keep their value: Fast group"
)


def _scenario(model=V2):
    scenario = load_scenario(str(FIXTURES / "corridor_simple.json"))
    scenario.model_type = model
    scenario.max_simulation_time = 5
    return scenario


def _two_area_scenario():
    """Area A ("Fast group") overrides V2 time_gap; area B inherits it."""
    import copy

    scenario = _scenario()
    raw_dists = scenario.raw["distributions"]
    a = raw_dists["jps-distributions_0"]
    a["name"] = "Fast group"
    a["parameters"]["number"] = 3
    b = copy.deepcopy(a)
    b["name"] = "Slow group"
    b["coordinates"] = [[0, 5], [4, 5], [4, 9], [0, 9], [0, 5]]
    raw_dists["jps-distributions_1"] = b
    scenario.set_agent_params(0, agent_parameter_overrides={V2: {"time_gap": 0.5}})
    return scenario


def _precedence_records(caplog):
    return [
        r
        for r in caplog.records
        if r.name == "jupedsim_scenarios" and r.levelno == logging.WARNING
        and "changes the default of" in r.getMessage()
    ]


def _overrides(scenario, did="jps-distributions_0"):
    return scenario.distributions[did]["parameters"].get(KEY)


def test_set_agent_params_merges_and_resets():
    scenario = _scenario()
    scenario.set_agent_params(0, agent_parameter_overrides={V2: {"time_gap": 2.0}})
    scenario.set_agent_params(
        0, agent_parameter_overrides={V2: {"strength_neighbor_repulsion": 1.0}}
    )
    assert _overrides(scenario) == {
        V2: {"time_gap": 2.0, "strength_neighbor_repulsion": 1.0}
    }
    scenario.set_agent_params(0, agent_parameter_overrides={V2: {"time_gap": None}})
    assert _overrides(scenario) == {V2: {"strength_neighbor_repulsion": 1.0}}
    scenario.set_agent_params(
        0, agent_parameter_overrides={V2: {"strength_neighbor_repulsion": None}}
    )
    assert KEY not in scenario.distributions["jps-distributions_0"]["parameters"]


@pytest.mark.parametrize("value", [True, np.bool_(True), "2.0"])
def test_set_agent_params_rejects_bool(value):
    scenario = _scenario()
    with pytest.raises(AgentParameterError):
        scenario.set_agent_params(0, agent_parameter_overrides={V2: {"time_gap": value}})
    assert _overrides(scenario) is None


def test_set_agent_params_rejects_non_mapping():
    scenario = _scenario()
    with pytest.raises(AgentParameterError):
        scenario.set_agent_params(0, agent_parameter_overrides={V2: 2.0})


def test_set_agent_params_stores_numpy_ints_as_python_numbers():
    scenario = _scenario()
    scenario.set_agent_params(0, agent_parameter_overrides={V2: {"time_gap": np.int64(2)}})
    stored = _overrides(scenario)[V2]["time_gap"]
    assert stored == 2 and type(stored) is int


def test_numpy_integers_validate_and_numpy_bool_is_rejected():
    data = {
        "distributions": {
            "jps-distributions_0": {
                "parameters": {KEY: {V2: {"time_gap": np.int64(2)}}},
            }
        }
    }
    settings = SimpleNamespace(time_gap=np.int64(3), strength_neighbor_repulsion=2.6,
                               range_neighbor_repulsion=0.1)
    validate_agent_parameters(data, V2, settings)
    data["distributions"]["jps-distributions_0"]["parameters"][KEY] = {}
    validate_agent_parameters(data, V2, settings)
    data["distributions"]["jps-distributions_0"]["parameters"][KEY] = {
        V2: {"time_gap": np.bool_(True)}
    }
    with pytest.raises(AgentParameterError, match='"time_gap"'):
        validate_agent_parameters(data, V2, settings)


def test_invalid_override_via_script_fails_before_placement(monkeypatch):
    scenario = _scenario()
    scenario.set_agent_params(0, agent_parameter_overrides={V2: {"time_gap": 50.0}})
    calls = []
    original = jps.Simulation.add_agent

    def spy(self, *args, **kwargs):
        calls.append(args)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(jps.Simulation, "add_agent", spy)
    with pytest.raises(AgentParameterError, match='"time_gap"'):
        run_scenario(scenario)
    assert calls == []


def test_overriding_areas_uses_active_model_only():
    scenario = _two_area_scenario()
    scenario.set_agent_params(1, agent_parameter_overrides={GCFM: {"b_min": 0.3}})
    assert scenario.overriding_areas("time_gap") == ["Fast group"]
    assert scenario.overriding_areas("b_min") == []
    scenario.model_type = GCFM
    assert scenario.overriding_areas("b_min") == ["Slow group"]


def test_set_model_params_warns_once_naming_overriders(caplog):
    scenario = _two_area_scenario()
    with caplog.at_level(logging.WARNING, logger="jupedsim_scenarios"):
        scenario.set_model_params(time_gap=2.0)
    records = _precedence_records(caplog)
    assert [r.getMessage() for r in records] == [WARNING_TEXT]


def test_set_model_params_no_warning_without_overriders(caplog):
    scenario = _two_area_scenario()
    with caplog.at_level(logging.WARNING, logger="jupedsim_scenarios"):
        scenario.set_model_params(range_neighbor_repulsion=0.2)
    assert _precedence_records(caplog) == []


def test_set_model_params_accepts_v2_geometry_keys():
    scenario = _scenario()
    scenario.set_model_params(
        v2_strength_geometry_repulsion=4.0, v2_range_geometry_repulsion=0.03
    )
    assert scenario.sim_params["v2_strength_geometry_repulsion"] == 4.0


def _resolved_time_gap(scenario, did):
    params = scenario.distributions[did]["parameters"]
    agent = create_agent_parameters(
        scenario.model_type, (0.0, 0.0), params, SimpleNamespace(**scenario.sim_params)
    )
    return agent.time_gap


def test_sweep_swept_default_reaches_non_overriders_only():
    base = _two_area_scenario()
    trials = []

    def apply(s, v):
        s.set_model_params(time_gap=v)
        trials.append(s)

    sweep = run_sweep(base, axes={"time_gap": [1.0, 2.0]}, apply={"time_gap": apply})
    assert len(sweep.trials) == 2
    assert [_resolved_time_gap(s, "jps-distributions_0") for s in trials] == [0.5, 0.5]
    assert [_resolved_time_gap(s, "jps-distributions_1") for s in trials] == [1.0, 2.0]


def test_sweep_warning_once_per_run(caplog):
    base = _two_area_scenario()
    with caplog.at_level(logging.WARNING, logger="jupedsim_scenarios"):
        run_sweep(
            base,
            axes={"time_gap": [1.0, 2.0]},
            apply={"time_gap": lambda s, v: s.set_model_params(time_gap=v)},
            seeds=[1, 2],
        )
    assert [r.getMessage() for r in _precedence_records(caplog)] == [WARNING_TEXT]


def test_sweep_cross_field_variant_fails_before_placement():
    base = _scenario(GCFM)
    base.set_agent_params(0, agent_parameter_overrides={GCFM: {"b_max": 0.3}})

    def apply(s, v):
        s.sim_params["b_min"] = v

    sweep = run_sweep(base, axes={"b_min": [0.4, 0.2]}, apply={"b_min": apply})
    failed, passed = sweep.trials
    assert failed.result.metrics["status"] == "error"
    assert "AgentParameterError" in failed.result.metrics["message"]
    assert '"b_max"' in failed.result.metrics["message"]
    assert passed.result.metrics["status"] != "error"


def test_factory_sweep_warning_once_per_run(caplog):
    base = _two_area_scenario()

    def factory(params):
        s = base.copy()
        s.sim_params["time_gap"] = params["time_gap"]
        return s

    with caplog.at_level(logging.WARNING, logger="jupedsim_scenarios"):
        run_sweep_from_factory(
            factory, trials=[{"time_gap": 1.0}, {"time_gap": 2.0}], seeds=[1, 2]
        )
    assert [r.getMessage() for r in _precedence_records(caplog)] == [WARNING_TEXT]
