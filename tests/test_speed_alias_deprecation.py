"""Deprecation contract for the ``v0`` → ``desired_speed`` rename.

``v0``, ``v0_std`` and ``v0_distribution`` were the original keys on
``Scenario.set_agent_params``; ``desired_speed*`` are now canonical and
the old spellings warn. The mirror onto the legacy keys in the
distribution params dict stays for one release so downstream consumers
that read raw JSON exports keep working.
"""

from __future__ import annotations

import warnings

import pytest

from jupedsim_scenarios import Scenario

SMALL_WKT = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"


def _scenario() -> Scenario:
    return Scenario(
        raw={"distributions": {"src": {"parameters": {}}}},
        walkable_area_wkt=SMALL_WKT,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )


def _params(s: Scenario) -> dict:
    return s.distributions["src"]["parameters"]


def test_v0_kwarg_warns_and_maps_to_desired_speed():
    s = _scenario()
    with pytest.warns(DeprecationWarning, match="'v0' is deprecated"):
        s.set_agent_params("src", v0=1.3)
    assert _params(s)["desired_speed"] == 1.3
    assert _params(s)["v0"] == 1.3  # legacy mirror retained for one release


def test_v0_std_and_v0_distribution_warn():
    s = _scenario()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        s.set_agent_params(
            "src", v0=1.0, v0_std=0.1, v0_distribution="gaussian"
        )
    messages = [str(w.message) for w in caught if w.category is DeprecationWarning]
    assert any("'v0' is deprecated" in m for m in messages)
    assert any("'v0_std' is deprecated" in m for m in messages)
    assert any("'v0_distribution' is deprecated" in m for m in messages)


def test_desired_speed_kwarg_is_silent():
    s = _scenario()
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        s.set_agent_params("src", desired_speed=1.1)
    assert _params(s)["desired_speed"] == 1.1


def test_conflicting_v0_and_desired_speed_raises():
    s = _scenario()
    with pytest.warns(DeprecationWarning), pytest.raises(TypeError, match="conflicting"):
        s.set_agent_params("src", desired_speed=1.0, v0=1.5)


def test_matching_v0_and_desired_speed_is_allowed():
    s = _scenario()
    with pytest.warns(DeprecationWarning):
        s.set_agent_params("src", desired_speed=1.2, v0=1.2)
    assert _params(s)["desired_speed"] == 1.2
