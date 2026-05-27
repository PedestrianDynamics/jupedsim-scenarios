"""Pin the documented safety multipliers in `simulation_init` (refs #53).

A previous undocumented `mean + 3*std` margin in ``_get_max_agent_radius``
silently rejected scenarios the Web-Based JuPedSim editor accepts (fixed
in PR #51). These tests pin the constants and ranges that survived the
audit so a future change that silently re-introduces a margin breaks a
test instead of a user's scenario.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("jupedsim")

from shapely.geometry import Polygon  # noqa: E402

from jupedsim_scenarios.simulation_init import (  # noqa: E402
    _estimate_max_capacity,
    _get_max_agent_radius,
    _normalize_speed_factor,
    _sample_agent_values,
)


def test_get_max_agent_radius_returns_mean_radius():
    # Regression for PR #51: the spacing radius must be the configured mean,
    # not mean + k*std. Gaussian samples above the mean are handled by the
    # simulator's dynamics phase, not by inflating the placement spacing.
    params = {"radius": 0.3, "radius_distribution": "gaussian", "radius_std": 0.05}
    assert _get_max_agent_radius(params) == 0.3


def test_estimate_max_capacity_uses_half_packing_density():
    # Pin the 0.5 random-packing factor documented in `_estimate_max_capacity`.
    polygon = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    radius = 0.2
    expected = math.floor(polygon.area / (math.pi * radius * radius) * 0.5)
    assert _estimate_max_capacity(polygon, radius) == expected


def test_estimate_max_capacity_floors_radius_at_0_1():
    # Pin the max(radius, 0.1) floor so a zero radius cannot blow up the
    # capacity estimate to infinity.
    polygon = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    assert _estimate_max_capacity(polygon, 0.0) == _estimate_max_capacity(polygon, 0.1)


def test_sample_agent_values_clamps_gaussian_mean_radius_to_1m():
    # Pin the [0.1, 1.0] m mean clamp documented in `_sample_agent_values`:
    # an oversized configured radius must collapse to <=1.0, not propagate.
    rng = np.random.RandomState(0)
    radii, _ = _sample_agent_values(
        {"radius": 2.0, "radius_distribution": "gaussian", "radius_std": 0.05},
        n_agents=200,
        rng=rng,
    )
    assert radii.max() <= 1.0
    assert radii.min() >= 0.1


def test_sample_agent_values_clamps_gaussian_mean_v0_to_5ms():
    # Pin the [0.1, 5.0] m/s mean clamp on desired speed.
    rng = np.random.RandomState(0)
    _, v0s = _sample_agent_values(
        {
            "radius": 0.2,
            "v0": 10.0,
            "v0_distribution": "gaussian",
            "v0_std": 0.1,
        },
        n_agents=200,
        rng=rng,
    )
    assert v0s.max() <= 5.0
    assert v0s.min() >= 0.1


def test_sample_agent_values_constant_radius_passes_through():
    # Constant (non-Gaussian) radii must NOT be clamped — any value JuPedSim
    # accepts is honored, per the docstring contract.
    rng = np.random.RandomState(0)
    radii, _ = _sample_agent_values({"radius": 2.0}, n_agents=5, rng=rng)
    assert (radii == 2.0).all()


def test_normalize_speed_factor_caps_at_3():
    # Pin the (unclear — pending audit) cap so a silent change is caught.
    assert _normalize_speed_factor(5.0) == 3.0
    assert _normalize_speed_factor(-1.0) == 1.0
    assert _normalize_speed_factor("not a number") == 1.0
    assert _normalize_speed_factor(2.5) == 2.5
