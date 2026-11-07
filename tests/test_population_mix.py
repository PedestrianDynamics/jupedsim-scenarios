"""Population mix validation and group attachment."""

from __future__ import annotations

import copy
import json
import pathlib
from types import SimpleNamespace

import jupedsim as jps
import pytest
import shapely

from jupedsim_scenarios import PopulationMixError, load_population_presets
from jupedsim_scenarios.population import (
    GROUPS_KEY,
    allocate_counts,
    attach_population_groups,
    validate_population,
)
from jupedsim_scenarios.simulation_init import initialize_simulation_from_json

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
KEY = "jps-distributions_0"


def _profile(v0=1.3, v0_std=0.2, radius=0.2):
    return {
        "desired_speed": {"mean": v0, "std": v0_std, "distribution": "gaussian"},
        "radius": {"mean": radius, "std": None, "distribution": "constant"},
    }


def _data(mix, params_as_str=False):
    params = {"number": 5, "radius": 0.2, "v0": 1.2}
    if mix is not None:
        params["population_mix"] = mix
    entry = {
        "type": "polygon",
        "coordinates": [[0, 0], [4, 0], [4, 5], [0, 5]],
        "parameters": json.dumps(params) if params_as_str else params,
    }
    return {
        "distributions": {KEY: entry},
        "population_profiles": {"a": _profile(), "b": _profile(1.0, 0.1, 0.25)},
    }


def _mix(sa=70, sb=30):
    return [{"profile": "a", "share": sa}, {"profile": "b", "share": sb}]


def test_allocate_counts_sums_to_n():
    assert allocate_counts([70, 30], 200) == [140, 60]
    assert allocate_counts([34, 33, 33], 10) == [4, 3, 3]
    assert allocate_counts([50, 50], 1) == [1, 0]
    assert allocate_counts([34, 33, 33], 2) == [1, 1, 0]


@pytest.mark.parametrize(
    "mix,msg",
    [
        ([{"profile": "a", "share": 70}, {"profile": "b", "share": 20}], "total 90 %"),
        ([{"profile": "a", "share": 0}, {"profile": "b", "share": 100}], "at least 1"),
        (
            [{"profile": "a", "share": 50}, {"profile": "zz", "share": 50}],
            "unknown population profile 'zz'",
        ),
        ([{"profile": "a", "share": 50}, {"profile": "a", "share": 50}], "more than once"),
        ([{"profile": "a", "share": 50.5}, {"profile": "b", "share": 49.5}], "whole number"),
    ],
)
def test_validate_rejects(mix, msg):
    with pytest.raises(PopulationMixError, match=msg) as err:
        validate_population(_data(mix))
    assert "Start 1" in str(err.value)


def test_attach_resolves_groups_in_mix_order():
    data = _data(_mix())
    validate_population(data)
    attach_population_groups(data)
    groups = data["distributions"][KEY]["parameters"][GROUPS_KEY]
    assert groups == [
        {
            "profile": "a",
            "share": 70,
            "radius": 0.2,
            "radius_distribution": "constant",
            "radius_std": None,
            "v0": 1.3,
            "v0_distribution": "gaussian",
            "v0_std": 0.2,
        },
        {
            "profile": "b",
            "share": 30,
            "radius": 0.25,
            "radius_distribution": "constant",
            "radius_std": None,
            "v0": 1.0,
            "v0_distribution": "gaussian",
            "v0_std": 0.1,
        },
    ]


def test_attach_handles_string_parameters():
    data = _data(_mix(), params_as_str=True)
    validate_population(data)
    attach_population_groups(data)
    params = data["distributions"][KEY]["parameters"]
    assert isinstance(params, dict)
    assert [g["profile"] for g in params[GROUPS_KEY]] == ["a", "b"]


def test_legacy_area_untouched():
    data = _data(None)
    before = copy.deepcopy(data)
    validate_population(data)
    attach_population_groups(data)
    assert data == before
    assert GROUPS_KEY not in data["distributions"][KEY]["parameters"]


def test_empty_mix_rejected():
    with pytest.raises(PopulationMixError, match="is empty"):
        validate_population(_data([]))


def test_boolean_share_rejected():
    mix = [{"profile": "a", "share": True}, {"profile": "b", "share": 99}]
    with pytest.raises(PopulationMixError, match="whole number"):
        validate_population(_data(mix))


@pytest.mark.parametrize(
    "profile_patch,msg",
    [
        ({"radius": None}, "radius is missing"),
        ({"desired_speed": {"mean": 1.3, "distribution": "uniform"}}, "not supported"),
        (
            {"desired_speed": {"mean": float("nan"), "distribution": "constant"}},
            "finite number above 0",
        ),
        ({"radius": {"mean": -0.2, "distribution": "constant"}}, "finite number above 0"),
        (
            {"desired_speed": {"mean": 1.3, "std": -0.1, "distribution": "gaussian"}},
            "at least 0",
        ),
    ],
)
def test_profile_values_rejected(profile_patch, msg):
    data = _data(_mix())
    data["population_profiles"]["a"].update(profile_patch)
    with pytest.raises(PopulationMixError, match=msg):
        validate_population(data)


def test_stale_groups_are_cleared():
    data = _data(None)
    data["distributions"][KEY]["parameters"][GROUPS_KEY] = [{"profile": "x"}]
    attach_population_groups(data)
    assert GROUPS_KEY not in data["distributions"][KEY]["parameters"]


def test_reattach_after_mix_change():
    data = _data(_mix(70, 30))
    attach_population_groups(data)
    data["distributions"][KEY]["parameters"]["population_mix"] = _mix(40, 60)
    attach_population_groups(data)
    groups = data["distributions"][KEY]["parameters"][GROUPS_KEY]
    assert [g["share"] for g in groups] == [40, 60]


def test_presets_load():
    assert "general_population" in load_population_presets()["profiles"]


def test_initialize_raises_before_placement(tmp_path):
    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    data["population_profiles"] = {"a": _profile(), "b": _profile()}
    params = data["distributions"][KEY]["parameters"]
    params["population_mix"] = _mix(70, 20)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    polygon = shapely.from_wkt(data["walkable_area_wkt"])
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=polygon)
    with pytest.raises(PopulationMixError, match="total 90 %"):
        initialize_simulation_from_json(
            str(config_path),
            simulation,
            SimpleNamespace(polygon=polygon),
        )
    assert simulation.agent_count() == 0


# -- direct setters on a mix area -------------------------------------------

MIX_PROFILE = {
    "desired_speed": {"mean": 1.2, "std": None, "distribution": "constant"},
    "radius": {"mean": 0.3, "std": None, "distribution": "constant"},
}
OWNED_MSG = (
    "radius and desired speed come from population_mix; "
    "remove the mix to set them directly"
)


def _mix_scenario(corridor_scenario):
    corridor_scenario.raw["population_profiles"] = {"a": MIX_PROFILE}
    params = corridor_scenario.distributions[KEY]["parameters"]
    params["population_mix"] = [{"profile": "a", "share": 100}]
    return corridor_scenario


@pytest.mark.parametrize(
    "kwargs",
    [
        {"radius": 0.25},
        {"radius_std": 0.01},
        {"radius_distribution": "gaussian"},
        {"desired_speed": 1.0},
        {"desired_speed_std": 0.1},
        {"desired_speed_distribution": "gaussian"},
        {"v0": 1.0},
    ],
)
def test_set_agent_params_rejects_owned_keys_on_mix_area(corridor_scenario, kwargs):
    scenario = _mix_scenario(corridor_scenario)
    with pytest.raises(PopulationMixError, match=OWNED_MSG):
        scenario.set_agent_params(0, **kwargs)


def test_set_agent_params_other_keys_work_on_mix_area(corridor_scenario):
    scenario = _mix_scenario(corridor_scenario)
    scenario.set_agent_params(0, number=7)
    assert scenario.distributions[KEY]["parameters"]["number"] == 7
