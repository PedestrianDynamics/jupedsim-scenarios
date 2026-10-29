"""Per-area agent parameter overrides are validated before any agent is placed.

The bounds below are copied from the spec's "Per-field bounds" table
(JuPedSim v1.4.2 ``CheckModelConstraint`` plus library bounds) rather than
read from ``FIELD_BOUNDS``, so a wrong entry in the library table fails here.
"""

from __future__ import annotations

import json
import math
import pathlib
from types import SimpleNamespace

import pytest

pytest.importorskip("jupedsim")

import jupedsim as jps
import shapely

from jupedsim_scenarios import AgentParameterError
from jupedsim_scenarios.agent_parameters import validate_agent_parameters
from jupedsim_scenarios.simulation_init import initialize_simulation_from_json

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

V1 = "CollisionFreeSpeedModel"
V2 = "CollisionFreeSpeedModelV2"
V3 = "CollisionFreeSpeedModelV3"
AVM = "AnticipationVelocityModel"
GCFM = "GeneralizedCentrifugalForceModel"
SFM = "SocialForceModel"
INF = math.inf

# (model, field, lo, lo_open, hi, hi_open); None = unbounded on that side.
SPEC_BOUNDS = [
    (V1, "time_gap", 0.1, False, 10, False),
    (V2, "time_gap", 0.1, False, 10, False),
    (V2, "strength_neighbor_repulsion", 0, False, None, False),
    (V2, "strength_geometry_repulsion", 0, False, None, False),
    (V2, "range_neighbor_repulsion", 0, True, None, False),
    (V2, "range_geometry_repulsion", 0, True, None, False),
    (V3, "time_gap", 0.1, False, 10, False),
    (V3, "strength_neighbor_repulsion", 0, False, None, False),
    (V3, "strength_geometry_repulsion", 0, False, None, False),
    (V3, "range_neighbor_repulsion", 0.01, False, None, False),
    (V3, "range_geometry_repulsion", 0.01, False, None, False),
    (V3, "range_x_scale", 0.01, False, None, False),
    (V3, "range_y_scale", 0.01, False, None, False),
    (V3, "theta_max_upper_bound", 0, False, math.pi, False),
    (V3, "agent_buffer", 0, False, 100, False),
    (AVM, "time_gap", 0, True, 10, False),
    (AVM, "strength_neighbor_repulsion", 0, False, 20, False),
    (AVM, "range_neighbor_repulsion", 0, True, 5, False),
    (AVM, "wall_buffer_distance", 0, False, 1, False),
    (AVM, "anticipation_time", 0, False, 5, False),
    (AVM, "reaction_time", 0, True, 1, False),
    (GCFM, "mass", 1, False, 100, False),
    (GCFM, "tau", 0.1, False, 10, False),
    (GCFM, "a_v", 0, False, 10, False),
    (GCFM, "a_min", 0.1, False, 1, False),
    (GCFM, "b_min", 0.1, False, 1, False),
    # b_max lower edge is the effective b_min (0.2 inherited by default).
    (GCFM, "b_max", 0.2, False, 2, False),
    (SFM, "mass", 0, True, None, False),
    (SFM, "reaction_time", 0, True, None, False),
    (SFM, "agent_scale", 0, False, None, False),
    (SFM, "obstacle_scale", 0, False, None, False),
    (SFM, "force_distance", 0, True, None, False),
]


def _edge_cases():
    for model, field, lo, lo_open, hi, hi_open in SPEC_BOUNDS:
        if lo is not None:
            inside = math.nextafter(lo, INF) if lo_open else lo
            outside = lo if lo_open else math.nextafter(lo, -INF)
            yield pytest.param(model, field, inside, outside, id=f"{model}-{field}-lo")
        if hi is not None:
            inside = math.nextafter(hi, -INF) if hi_open else hi
            outside = hi if hi_open else math.nextafter(hi, INF)
            yield pytest.param(model, field, inside, outside, id=f"{model}-{field}-hi")


def _data(overrides, key="jps-distributions_0", name=None):
    entry = {
        "type": "polygon",
        "coordinates": [[0, 0], [4, 0], [4, 5], [0, 5]],
        "parameters": {"number": 5, "radius": 0.2, "v0": 1.2},
    }
    if overrides is not None:
        entry["parameters"]["agent_parameter_overrides"] = overrides
    if name is not None:
        entry["name"] = name
    return {"distributions": {key: entry}}


def _area_map(model, field, value):
    fields = {field: value}
    # b_min's upper edge would trip the cross-field rule against the
    # inherited b_max of 0.4.
    if model == GCFM and field == "b_min":
        fields["b_max"] = 2
    return {model: fields}


@pytest.mark.parametrize(("model", "field", "inside", "outside"), _edge_cases())
def test_bounds_edges(model, field, inside, outside):
    validate_agent_parameters(_data(_area_map(model, field, inside)), model, None)
    with pytest.raises(AgentParameterError, match=f'"{field}"'):
        validate_agent_parameters(_data(_area_map(model, field, outside)), model, None)


@pytest.mark.parametrize("value", [True, math.nan, math.inf, -math.inf])
def test_rejects_bool_nan_inf(value):
    data = _data({V2: {"strength_neighbor_repulsion": value}})
    with pytest.raises(AgentParameterError, match='"strength_neighbor_repulsion"'):
        validate_agent_parameters(data, V2, None)


def test_unknown_field_names_area():
    overrides = {V2: {"strenght_neighbor_repulsion": 1}}
    data = _data(overrides, key="jps-distributions_2", name="Fast group")
    with pytest.raises(AgentParameterError) as exc_info:
        validate_agent_parameters(data, V2, None)
    msg = str(exc_info.value)
    for part in ("jps-distributions_2", '"Fast group"', V2, '"strenght_neighbor_repulsion"'):
        assert part in msg, msg

    unnamed = _data(overrides, key="jps-distributions_2")
    with pytest.raises(AgentParameterError, match='"Start 3"'):
        validate_agent_parameters(unnamed, V2, None)


def test_model_wide_field_rejected():
    data = _data({V1: {"strength_neighbor_repulsion": 2.0}})
    with pytest.raises(AgentParameterError, match='"strength_neighbor_repulsion"'):
        validate_agent_parameters(data, V1, None)


def test_unknown_gcfm_field_rejected_before_resolving():
    data = _data({GCFM: {"b_maxx": 1.0}})
    with pytest.raises(AgentParameterError, match='"b_maxx"'):
        validate_agent_parameters(data, GCFM, None)


@pytest.mark.parametrize("field", ["radius", "desired_speed"])
@pytest.mark.parametrize("model", [V2, SFM])
def test_radius_in_map_rejected(model, field):
    data = _data({model: {field: 0.3}})
    with pytest.raises(AgentParameterError, match=f'"{field}"'):
        validate_agent_parameters(data, V2, None)


def test_non_mapping_rejected():
    with pytest.raises(AgentParameterError):
        validate_agent_parameters(_data({V2: 1.0}), V2, None)
    with pytest.raises(AgentParameterError):
        validate_agent_parameters(_data([1.0]), V2, None)


def test_inactive_model_value_must_be_number():
    data = _data({SFM: {"mass": "heavy"}})
    with pytest.raises(AgentParameterError, match='"mass"'):
        validate_agent_parameters(data, V2, None)


def test_inactive_model_not_bounds_checked():
    validate_agent_parameters(_data({SFM: {"mass": 0}}), V2, None)


def test_no_overrides_is_valid():
    validate_agent_parameters(_data(None), V2, None)
    validate_agent_parameters({"distributions": {}}, V2, None)
    validate_agent_parameters({}, V2, None)


def test_string_encoded_parameters_are_decoded():
    data = _data({V2: {"time_gap": 20}})
    entry = data["distributions"]["jps-distributions_0"]
    entry["parameters"] = json.dumps(entry["parameters"])
    with pytest.raises(AgentParameterError, match='"time_gap"'):
        validate_agent_parameters(data, V2, None)


def test_invalid_inherited_default_fails_every_area():
    settings = SimpleNamespace(time_gap=20)
    with pytest.raises(AgentParameterError, match='"time_gap"'):
        validate_agent_parameters(_data(None), V2, settings)


def test_gcfm_cross_field_uses_effective_b_min():
    settings = SimpleNamespace(b_min=0.4)
    data = _data({GCFM: {"b_max": 0.3}})
    with pytest.raises(AgentParameterError, match='"b_max"'):
        validate_agent_parameters(data, GCFM, settings)


def test_flow_area_invalid_fails_before_run(tmp_path):
    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    params = data["distributions"]["jps-distributions_0"]["parameters"]
    params["use_flow_spawning"] = True
    params["agent_parameter_overrides"] = {V2: {"time_gap": 0.0}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(data))

    polygon = shapely.from_wkt(data["walkable_area_wkt"])
    simulation = jps.Simulation(
        model=jps.CollisionFreeSpeedModelV2(), geometry=polygon
    )
    with pytest.raises(AgentParameterError, match="jps-distributions_0"):
        initialize_simulation_from_json(
            str(config_path),
            simulation,
            SimpleNamespace(polygon=polygon),
            model_type=V2,
        )
    assert simulation.agent_count() == 0


def test_inherited_invalid_value_names_setting():
    settings = SimpleNamespace(relaxation_time=0)
    with pytest.raises(AgentParameterError) as exc_info:
        validate_agent_parameters(_data(None), SFM, settings)
    assert 'inherited from setting "relaxation_time"' in str(exc_info.value)


def test_overridden_invalid_value_has_no_inherited_note():
    data = _data({SFM: {"reaction_time": 0}})
    with pytest.raises(AgentParameterError) as exc_info:
        validate_agent_parameters(data, SFM, SimpleNamespace())
    assert "inherited" not in str(exc_info.value)


def test_inherited_note_uses_first_present_settings_key():
    settings = SimpleNamespace(s0=0)
    with pytest.raises(AgentParameterError) as exc_info:
        validate_agent_parameters(_data(None), AVM, settings)
    assert 'inherited from setting "s0"' in str(exc_info.value)


def test_gcfm_cross_field_names_inherited_b_min():
    settings = SimpleNamespace(b_min=0.4)
    data = _data({GCFM: {"b_max": 0.3}})
    with pytest.raises(AgentParameterError) as exc_info:
        validate_agent_parameters(data, GCFM, settings)
    msg = str(exc_info.value)
    assert 'inherited from setting "b_min"' in msg, msg
    assert 'inherited from setting "b_max"' not in msg, msg


def test_gcfm_cross_field_names_inherited_b_max():
    settings = SimpleNamespace(b_max=0.3)
    data = _data({GCFM: {"b_min": 0.4}})
    with pytest.raises(AgentParameterError) as exc_info:
        validate_agent_parameters(data, GCFM, settings)
    msg = str(exc_info.value)
    assert 'inherited from setting "b_max"' in msg, msg
    assert 'inherited from setting "b_min"' not in msg, msg
