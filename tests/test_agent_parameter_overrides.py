"""Per-area agent parameter overrides resolve in create_agent_parameters."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

jps = pytest.importorskip("jupedsim")

from jupedsim_scenarios.agent_parameters import (  # noqa: E402
    FIELD_BOUNDS,
    OVERRIDES_KEY,
    PER_AGENT_FIELDS,
    active_overrides,
    settings_key_fields,
)
from jupedsim_scenarios.simulation_init import create_agent_parameters  # noqa: E402

EXCLUDED = {
    "radius",
    "desired_speed",
    "position",
    "journey_id",
    "stage_id",
    "orientation",
    "velocity",
    "speed",
    "desired_direction",
}

MODELS_WITH_FIELDS = [
    "CollisionFreeSpeedModel",
    "CollisionFreeSpeedModelV2",
    "CollisionFreeSpeedModelV3",
    "AnticipationVelocityModel",
    "GeneralizedCentrifugalForceModel",
    "SocialForceModel",
]

ALL_MODELS = MODELS_WITH_FIELDS + ["WarpDriverModel"]


def _first_field(model):
    field, (keys, fallback) = next(iter(PER_AGENT_FIELDS[model].items()))
    return field, keys, fallback


def _in_bounds_value(model, field, avoid):
    """A value inside the field's bounds that differs from ``avoid``."""
    bound = FIELD_BOUNDS[model][field]
    candidates = [0.35, 0.45, 0.55, 0.15, 3.0]
    for value in candidates:
        if value == avoid:
            continue
        if bound.lo is not None and (value < bound.lo or (bound.lo_open and value == bound.lo)):
            continue
        if bound.hi is not None and (value > bound.hi or (bound.hi_open and value == bound.hi)):
            continue
        return value
    raise AssertionError(f"no in-bounds candidate for {model}.{field}")


def _params(overrides=None):
    params = {"radius": 0.2, "v0": 1.2}
    if overrides is not None:
        params[OVERRIDES_KEY] = overrides
    return params


@pytest.mark.parametrize("model", MODELS_WITH_FIELDS)
def test_override_used(model):
    field, keys, fallback = _first_field(model)
    value = _in_bounds_value(model, field, fallback)
    global_params = SimpleNamespace(**{keys[0]: fallback})
    agent = create_agent_parameters(
        model, (0.0, 0.0), _params({model: {field: value}}), global_params
    )
    assert getattr(agent, field) == value


@pytest.mark.parametrize("model", MODELS_WITH_FIELDS)
def test_absent_uses_setting(model):
    field, keys, fallback = _first_field(model)
    setting = _in_bounds_value(model, field, fallback)
    global_params = SimpleNamespace(**{keys[0]: setting})
    agent = create_agent_parameters(model, (0.0, 0.0), _params(), global_params)
    assert getattr(agent, field) == setting


def test_other_model_override_ignored():
    global_params = SimpleNamespace(time_gap=1.4)
    params = _params({"AnticipationVelocityModel": {"time_gap": 3.0}})
    agent = create_agent_parameters("CollisionFreeSpeedModelV2", (0.0, 0.0), params, global_params)
    assert agent.time_gap == 1.4


def test_avm_override_beats_both_spellings():
    global_params = SimpleNamespace(T=1.0, anticipation_time=2.0)
    params = _params({"AnticipationVelocityModel": {"anticipation_time": 3.0}})
    agent = create_agent_parameters("AnticipationVelocityModel", (0.0, 0.0), params, global_params)
    assert agent.anticipation_time == 3.0


def test_v2_geometry_repulsion_settings_read():
    global_params = SimpleNamespace(
        v2_strength_geometry_repulsion=4.0, v2_range_geometry_repulsion=0.05
    )
    agent = create_agent_parameters(
        "CollisionFreeSpeedModelV2", (0.0, 0.0), _params(), global_params
    )
    assert agent.strength_geometry_repulsion == 4.0
    assert agent.range_geometry_repulsion == 0.05


def test_v2_geometry_repulsion_missing_keeps_jupedsim_default():
    default = jps.CollisionFreeSpeedModelV2AgentParameters()
    agent = create_agent_parameters(
        "CollisionFreeSpeedModelV2", (0.0, 0.0), _params(), SimpleNamespace()
    )
    assert agent.strength_geometry_repulsion == default.strength_geometry_repulsion
    assert agent.range_geometry_repulsion == default.range_geometry_repulsion


@pytest.mark.parametrize("model", ALL_MODELS)
def test_table_matches_dataclasses(model):
    dataclass = getattr(jps, f"{model}AgentParameters")
    expected = {f.name for f in dataclasses.fields(dataclass)} - EXCLUDED
    assert set(PER_AGENT_FIELDS.get(model, {})) == expected
    assert set(FIELD_BOUNDS.get(model, {})) == expected


def test_active_overrides_absent_is_empty():
    assert active_overrides({}, "SocialForceModel") == {}
    assert active_overrides({OVERRIDES_KEY: {}}, "SocialForceModel") == {}
    assert active_overrides(
        {OVERRIDES_KEY: {"SocialForceModel": {"mass": 70.0}}}, "SocialForceModel"
    ) == {"mass": 70.0}


def test_settings_key_fields():
    keys = settings_key_fields("AnticipationVelocityModel")
    assert keys["T"] == "anticipation_time"
    assert keys["anticipation_time"] == "anticipation_time"
    assert keys["s0"] == "reaction_time"
    assert keys["avm_time_gap"] == "time_gap"
    assert settings_key_fields("SocialForceModel")["agent_strength"] == "agent_scale"
    assert settings_key_fields("WarpDriverModel") == {}
