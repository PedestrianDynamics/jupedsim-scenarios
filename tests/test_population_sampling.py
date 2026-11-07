"""Per-profile sampling of fixed-count and fill-area spawn areas."""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import jupedsim as jps
import numpy as np
import shapely

from jupedsim_scenarios.population import GROUPS_KEY, allocate_counts
from jupedsim_scenarios.simulation_init import (
    _get_max_agent_radius,
    _sample_agent_values,
    initialize_simulation_from_json,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
KEY = "jps-distributions_0"


def _group(
    profile,
    share,
    v0=1.2,
    radius=0.2,
    v0_std=None,
    radius_std=None,
    v0_dist=None,
    radius_dist="constant",
):
    return {
        "profile": profile,
        "share": share,
        "radius": radius,
        "radius_distribution": radius_dist,
        "radius_std": radius_std,
        "v0": v0,
        "v0_distribution": v0_dist or ("gaussian" if v0_std else "constant"),
        "v0_std": v0_std,
    }


def _with_groups(specs, **extra):
    """specs: (profile, share, v0) with constant radius and speed."""
    groups = [_group(p, s, v0=v) for p, s, v in specs]
    return {GROUPS_KEY: groups, **extra}


def test_two_constant_profiles_exact_counts_no_averaging():
    params = _with_groups([("slow", 70, 0.8), ("fast", 30, 1.6)])
    _, v0s = _sample_agent_values(params, 200, np.random.RandomState(1))
    assert sorted(set(v0s)) == [0.8, 1.6]
    assert (v0s == 0.8).sum() == 140 and (v0s == 1.6).sum() == 60


def test_single_group_is_bit_identical_to_legacy():
    legacy = {
        "radius": 0.2,
        "radius_distribution": "gaussian",
        "radius_std": 0.02,
        "v0": 1.3,
        "v0_distribution": "gaussian",
        "v0_std": 0.2,
    }
    grouped = {
        GROUPS_KEY: [
            _group(
                "p", 100, v0=1.3, v0_std=0.2, radius=0.2, radius_std=0.02, radius_dist="gaussian"
            )
        ]
    }
    a = _sample_agent_values(legacy, 50, np.random.RandomState(7))
    b = _sample_agent_values(grouped, 50, np.random.RandomState(7))
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])


def test_mix_ignores_legacy_fields():
    params = _with_groups(
        [("a", 50, 1.0), ("b", 50, 1.5)],
        v0=9.9,
        desired_speed=9.9,
        desired_speed_std=1.0,
        desired_speed_distribution="gaussian",
        radius=0.9,
    )
    radii, v0s = _sample_agent_values(params, 100, np.random.RandomState(3))
    assert sorted(set(v0s)) == [1.0, 1.5]
    assert set(radii) == {0.2}


def test_mix_same_seed_same_result():
    params = _with_groups([("a", 60, 1.0), ("b", 40, 1.5)])
    a = _sample_agent_values(params, 80, np.random.RandomState(5))
    b = _sample_agent_values(params, 80, np.random.RandomState(5))
    np.testing.assert_array_equal(a[1], b[1])
    c = _sample_agent_values(params, 80, np.random.RandomState(6))
    assert not np.array_equal(a[1], c[1])


def test_group_mean_outside_clip_is_clamped():
    group = _group("big", 50, radius=1.5, radius_std=0.1, radius_dist="gaussian")
    params = {GROUPS_KEY: [group, _group("small", 50)]}
    radii, _ = _sample_agent_values(params, 2000, np.random.RandomState(0))
    big = radii[radii != 0.2]
    assert big.min() >= 0.1 and big.max() <= 1.0
    assert big.std() > 0


def test_max_radius_uses_largest_group_mean():
    params = {GROUPS_KEY: [_group("a", 50, radius=0.2), _group("b", 50, radius=0.25)]}
    assert _get_max_agent_radius(params) == 0.25


def test_max_radius_uses_effective_mean():
    group = _group("g", 100, radius=1.5, radius_std=0.1, radius_dist="gaussian")
    assert _get_max_agent_radius({GROUPS_KEY: [group]}) == 1.0


def test_fill_area_allocates_on_placed_count(tmp_path):
    data = json.loads((FIXTURES / "corridor_simple.json").read_text())

    def profile(radius):
        return {
            "desired_speed": {"mean": 1.2, "std": None, "distribution": "constant"},
            "radius": {"mean": radius, "std": None, "distribution": "constant"},
        }

    data["population_profiles"] = {"a": profile(0.15), "b": profile(0.2)}
    params = data["distributions"][KEY]["parameters"]
    params.update(distribution_mode="by_percentage", percentage=40)
    params["population_mix"] = [
        {"profile": "a", "share": 70},
        {"profile": "b", "share": 30},
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    polygon = shapely.from_wkt(data["walkable_area_wkt"])
    simulation = jps.Simulation(model=jps.CollisionFreeSpeedModel(), geometry=polygon)
    _, positions, agent_radii, _ = initialize_simulation_from_json(
        str(config_path), simulation, SimpleNamespace(polygon=polygon)
    )
    placed = simulation.agent_count()
    radii = list(agent_radii.values())
    assert placed == len(positions) > 10
    assert radii.count(0.15) + radii.count(0.2) == placed
    assert radii.count(0.15) == allocate_counts([70, 30], placed)[0]


def test_sampling_statistics_match_profile():
    # 4 standard errors of the sample mean / std with a deterministic seed;
    # the clip at [0.1, 5.0] m/s is >4 sigma away, so its effect is < 1e-4.
    mean, std, n = 1.45, 0.28, 10_000
    params = {GROUPS_KEY: [_group("g", 100, v0=mean, v0_std=std)]}
    _, v0s = _sample_agent_values(params, n, np.random.RandomState(0))
    assert abs(v0s.mean() - mean) < 4 * std / np.sqrt(n)
    assert abs(v0s.std() - std) < 4 * std / np.sqrt(2 * n)
