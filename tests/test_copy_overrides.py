"""Scenario.copy() override semantics.

Overrides replace fields outright. The dict-valued ``sim_params`` field
has a guardrail: a replacement that drops existing keys raises
``TypeError`` so accidental partial overrides surface instead of
silently shrinking the params dict.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import Scenario

SMALL_WKT = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"


def _scenario() -> Scenario:
    return Scenario(
        raw={},
        walkable_area_wkt=SMALL_WKT,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60, "extra_knob": 1.5},
    )


def test_copy_without_overrides_is_independent():
    s = _scenario()
    clone = s.copy()
    clone.sim_params["max_simulation_time"] = 999
    assert s.sim_params["max_simulation_time"] == 60


def test_copy_scalar_override_works():
    s = _scenario()
    clone = s.copy(seed=7, model_type="SocialForceModel")
    assert clone.seed == 7
    assert clone.model_type == "SocialForceModel"
    assert s.seed == 42


def test_copy_sim_params_dropping_keys_raises():
    s = _scenario()
    with pytest.raises(TypeError, match="would drop existing keys"):
        s.copy(sim_params={"max_simulation_time": 60})  # extra_knob dropped


def test_copy_sim_params_full_replacement_allowed():
    s = _scenario()
    clone = s.copy(
        sim_params={"max_simulation_time": 120, "extra_knob": 2.5, "added": "ok"}
    )
    assert clone.sim_params == {
        "max_simulation_time": 120,
        "extra_knob": 2.5,
        "added": "ok",
    }


def test_copy_unknown_attribute_raises():
    s = _scenario()
    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        s.copy(nope=1)
