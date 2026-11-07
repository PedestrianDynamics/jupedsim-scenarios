"""Every spawned agent records the population profile it was drawn from."""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import jupedsim as jps
import numpy as np
import pytest
import shapely

import jupedsim_scenarios as js
from jupedsim_scenarios.population import GROUPS_KEY, allocate_counts
from jupedsim_scenarios.simulation_init import (
    _sample_agent_values,
    _sample_agent_values_with_profiles,
    initialize_simulation_from_json,
    sample_flow_arrival,
    sample_flow_arrival_with_profile,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
KEY = "jps-distributions_0"

LEGACY = {
    "radius": 0.2,
    "radius_distribution": "gaussian",
    "radius_std": 0.03,
    "v0": 1.3,
    "v0_distribution": "gaussian",
    "v0_std": 0.2,
}


def _group(profile, share, v0, radius=0.2):
    return {
        "profile": profile,
        "share": share,
        "radius": radius,
        "radius_distribution": "constant",
        "radius_std": None,
        "v0": v0,
        "v0_distribution": "gaussian",
        "v0_std": 0.1,
    }


MIX = {GROUPS_KEY: [_group("slow", 70, 0.8), _group("fast", 30, 1.6, radius=0.25)]}
SINGLE = {GROUPS_KEY: [_group("only", 100, 1.2)]}


@pytest.mark.parametrize("params", [LEGACY, SINGLE, MIX], ids=["legacy", "single", "mix"])
def test_profiles_variant_keeps_values_and_rng_stream(params):
    rng_a, rng_b = np.random.RandomState(4), np.random.RandomState(4)
    radii, v0s, _ = _sample_agent_values_with_profiles(params, 60, rng_a)
    ref_radii, ref_v0s = _sample_agent_values(params, 60, rng_b)
    np.testing.assert_array_equal(radii, ref_radii)
    np.testing.assert_array_equal(v0s, ref_v0s)
    assert rng_a.random_sample() == rng_b.random_sample()


def test_legacy_area_has_no_profile():
    _, _, profiles = _sample_agent_values_with_profiles(LEGACY, 5, np.random.RandomState(0))
    assert profiles == [None] * 5


def test_single_group_labels_every_agent():
    _, _, profiles = _sample_agent_values_with_profiles(SINGLE, 5, np.random.RandomState(0))
    assert profiles == ["only"] * 5


def test_mix_profiles_match_sampled_values():
    radii, _, profiles = _sample_agent_values_with_profiles(MIX, 100, np.random.RandomState(2))
    assert profiles.count("slow") == 70 and profiles.count("fast") == 30
    for radius, profile in zip(radii, profiles, strict=True):
        assert radius == (0.2 if profile == "slow" else 0.25)


@pytest.mark.parametrize("params", [LEGACY, SINGLE, MIX], ids=["legacy", "single", "mix"])
def test_flow_profile_variant_keeps_values_and_rng_stream(params):
    rng_a, rng_b = np.random.RandomState(9), np.random.RandomState(9)
    for _ in range(20):
        r, v, _ = sample_flow_arrival_with_profile(params, rng_a)
        assert (r, v) == sample_flow_arrival(params, rng_b)
    assert rng_a.random_sample() == rng_b.random_sample()


def test_flow_arrival_profile_matches_drawn_group():
    rng = np.random.RandomState(1)
    arrivals = [sample_flow_arrival_with_profile(MIX, rng) for _ in range(200)]
    assert {p for _, _, p in arrivals} == {"slow", "fast"}
    for r, _, p in arrivals:
        assert r == (0.2 if p == "slow" else 0.25)
    assert sample_flow_arrival_with_profile(LEGACY, rng)[2] is None


def test_flow_profile_sampler_is_exported():
    assert js.sample_flow_arrival_with_profile is sample_flow_arrival_with_profile


def _profile(radius):
    return {
        "desired_speed": {"mean": 1.2, "std": None, "distribution": "constant"},
        "radius": {"mean": radius, "std": None, "distribution": "constant"},
    }


def _drop_journeys(data):
    data.pop("journeys_v2", None)


def _journeyless_area(data):
    # The v2 path needs one area with a journey; the mixed area has none.
    routed = json.loads(json.dumps(data["distributions"][KEY]))
    routed["coordinates"] = [[8, 0], [12, 0], [12, 5], [8, 5], [8, 0]]
    routed["parameters"] = {"number": 5, "radius": 0.3, "v0": 1.2}
    data["distributions"]["jps-distributions_1"] = routed
    data["distributions"][KEY].pop("journey_weights")


@pytest.mark.parametrize(
    "patch",
    [None, _journeyless_area, _drop_journeys],
    ids=["journeys_v2", "journeyless_v2", "fallback"],
)
def test_spawned_agents_record_profile(tmp_path, patch):
    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    data["population_profiles"] = {"a": _profile(0.15), "b": _profile(0.2)}
    params = data["distributions"][KEY]["parameters"]
    params["number"] = 20
    params["population_mix"] = [{"profile": "a", "share": 70}, {"profile": "b", "share": 30}]
    if patch:
        patch(data)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))

    polygon = shapely.from_wkt(data["walkable_area_wkt"])
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=polygon)
    _, _, agent_radii, spawning_info = initialize_simulation_from_json(
        str(path), simulation, SimpleNamespace(polygon=polygon)
    )
    profiles = spawning_info["agent_profiles"]
    assert profiles.keys() == agent_radii.keys()
    expected = {0.15: "a", 0.2: "b", 0.3: None}
    for agent_id, radius in agent_radii.items():
        assert profiles[agent_id] == expected[radius]
    labels = [p for p in profiles.values() if p is not None]
    assert len(labels) == 20
    assert labels.count("a") == allocate_counts([70, 30], len(labels))[0]


def test_legacy_area_records_none(tmp_path):
    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    polygon = shapely.from_wkt(data["walkable_area_wkt"])
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=polygon)
    _, _, agent_radii, spawning_info = initialize_simulation_from_json(
        str(path), simulation, SimpleNamespace(polygon=polygon)
    )
    profiles = spawning_info["agent_profiles"]
    assert profiles.keys() == agent_radii.keys()
    assert set(profiles.values()) == {None}
