"""Per-agent parameter fields, their settings keys, bounds and overrides.

A spawn area may carry ``agent_parameter_overrides``, shaped
``{"<model_type>": {"<jupedsim_field>": <number>}}``. Only the entry for the
active model applies; absent means the area inherits the global settings.
"""

from __future__ import annotations

import json
import math
import numbers
from dataclasses import dataclass

import numpy as np

OVERRIDES_KEY = "agent_parameter_overrides"

# Per-agent CollisionFreeSpeedModelV3 fields read from ``v3_<field>`` settings;
# defaults equal JuPedSim's own dataclass defaults.
_V3_AGENT_DEFAULTS = {
    "time_gap": 1.0,
    "strength_neighbor_repulsion": 8.0,
    "range_neighbor_repulsion": 0.1,
    "strength_geometry_repulsion": 5.0,
    "range_geometry_repulsion": 0.02,
    "range_x_scale": 20.0,
    "range_y_scale": 8.0,
    "theta_max_upper_bound": 1.57,
    "agent_buffer": 0.0,
}

# Per-agent AnticipationVelocityModel fields read from ``avm_<field>`` settings.
_AVM_AGENT_DEFAULTS = {
    "time_gap": 1.06,
    "strength_neighbor_repulsion": 8.0,
    "range_neighbor_repulsion": 0.1,
    "wall_buffer_distance": 0.1,
}

# model -> field -> (settings keys in precedence order, fallback when unset).
PER_AGENT_FIELDS: dict[str, dict[str, tuple[tuple[str, ...], float]]] = {
    "CollisionFreeSpeedModel": {
        "time_gap": (("csm_time_gap",), 1.0),
    },
    "CollisionFreeSpeedModelV2": {
        "time_gap": (("time_gap",), 1.0),
        "strength_neighbor_repulsion": (("strength_neighbor_repulsion",), 2.6),
        "range_neighbor_repulsion": (("range_neighbor_repulsion",), 0.1),
        "strength_geometry_repulsion": (("v2_strength_geometry_repulsion",), 5.0),
        "range_geometry_repulsion": (("v2_range_geometry_repulsion",), 0.02),
    },
    "CollisionFreeSpeedModelV3": {
        field: ((f"v3_{field}",), default) for field, default in _V3_AGENT_DEFAULTS.items()
    },
    "AnticipationVelocityModel": {
        **{field: ((f"avm_{field}",), default) for field, default in _AVM_AGENT_DEFAULTS.items()},
        "anticipation_time": (("anticipation_time", "T"), 1.0),
        "reaction_time": (("reaction_time", "s0"), 0.3),
    },
    "GeneralizedCentrifugalForceModel": {
        "mass": (("mass",), 80.0),
        "tau": (("tau",), 0.5),
        "a_v": (("a_v",), 1.0),
        "a_min": (("a_min",), 0.2),
        "b_min": (("b_min",), 0.2),
        "b_max": (("b_max",), 0.4),
    },
    "SocialForceModel": {
        "reaction_time": (("relaxation_time",), 0.5),
        "agent_scale": (("agent_strength",), 2000),
        "force_distance": (("agent_range",), 0.08),
        "mass": (("mass",), 80.0),
        "obstacle_scale": (("sfm_obstacle_scale",), 2000),
    },
    "WarpDriverModel": {},
}


@dataclass(frozen=True)
class Bound:
    """Closed or open interval; ``None`` means unbounded on that side."""

    lo: float | None
    hi: float | None
    lo_open: bool
    hi_open: bool


_TIME_GAP = Bound(0.1, 10, False, False)
_NON_NEGATIVE = Bound(0, None, False, False)
_POSITIVE = Bound(0, None, True, False)
_V3_MIN_RANGE = Bound(0.01, None, False, False)

# JuPedSim v1.4.2 CheckModelConstraint, plus library bounds for divisors and
# quantities that cannot be negative. GCFM b_max >= b_min is cross-field and
# is checked separately.
FIELD_BOUNDS: dict[str, dict[str, Bound]] = {
    "CollisionFreeSpeedModel": {
        "time_gap": _TIME_GAP,
    },
    "CollisionFreeSpeedModelV2": {
        "time_gap": _TIME_GAP,
        "strength_neighbor_repulsion": _NON_NEGATIVE,
        "range_neighbor_repulsion": _POSITIVE,
        "strength_geometry_repulsion": _NON_NEGATIVE,
        "range_geometry_repulsion": _POSITIVE,
    },
    "CollisionFreeSpeedModelV3": {
        "time_gap": _TIME_GAP,
        "strength_neighbor_repulsion": _NON_NEGATIVE,
        "range_neighbor_repulsion": _V3_MIN_RANGE,
        "strength_geometry_repulsion": _NON_NEGATIVE,
        "range_geometry_repulsion": _V3_MIN_RANGE,
        "range_x_scale": _V3_MIN_RANGE,
        "range_y_scale": _V3_MIN_RANGE,
        "theta_max_upper_bound": Bound(0, math.pi, False, False),
        "agent_buffer": Bound(0, 100, False, False),
    },
    "AnticipationVelocityModel": {
        "time_gap": Bound(0, 10, True, False),
        "strength_neighbor_repulsion": Bound(0, 20, False, False),
        "range_neighbor_repulsion": Bound(0, 5, True, False),
        "wall_buffer_distance": Bound(0, 1, False, False),
        "anticipation_time": Bound(0, 5, False, False),
        "reaction_time": Bound(0, 1, True, False),
    },
    "GeneralizedCentrifugalForceModel": {
        "mass": Bound(1, 100, False, False),
        "tau": Bound(0.1, 10, False, False),
        "a_v": Bound(0, 10, False, False),
        "a_min": Bound(0.1, 1, False, False),
        "b_min": Bound(0.1, 1, False, False),
        "b_max": Bound(None, 2, False, False),
    },
    "SocialForceModel": {
        "reaction_time": _POSITIVE,
        "agent_scale": _NON_NEGATIVE,
        "force_distance": _POSITIVE,
        "mass": _POSITIVE,
        "obstacle_scale": _NON_NEGATIVE,
    },
    "WarpDriverModel": {},
}


def active_overrides(params: dict, model_type: str) -> dict[str, float]:
    """Return the area's overrides for ``model_type``; ``{}`` when absent."""
    overrides = params.get(OVERRIDES_KEY) or {}
    return dict(overrides.get(model_type) or {})


def settings_key_fields(model_type: str) -> dict[str, str]:
    """Map each settings key of ``model_type`` to the field it sets."""
    return {
        key: field
        for field, (keys, _fallback) in PER_AGENT_FIELDS.get(model_type, {}).items()
        for key in keys
    }


# Fields no override may set, for any model.
_EXCLUDED_FIELDS = ("radius", "desired_speed")


class AgentParameterError(ValueError):
    """A spawn area's agent parameters are invalid; the run does not start."""


def _is_number(value) -> bool:
    """A real number (numpy scalars included), never a boolean."""
    return isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_))


def _area_label(key: str, entry: dict) -> str:
    """Display name of a spawn area: its ``name``, else ``Start {N+1}``."""
    name = entry.get("name")
    if isinstance(name, str) and name.strip():
        return name
    suffix = str(key).rsplit("_", 1)[-1]
    return f"Start {int(suffix) + 1}" if suffix.isdigit() else str(key)


def _area_params(entry: dict) -> dict:
    params = entry.get("parameters") or {}
    if isinstance(params, str):
        params = json.loads(params)
    return params


def overriding_area_labels(distributions, model_type: str, field: str) -> list[str]:
    """Labels of the spawn areas whose ``model_type`` overrides set ``field``."""
    return [
        _area_label(key, entry)
        for key, entry in distributions.items()
        if field in active_overrides(_area_params(entry), model_type)
    ]


def precedence_warning(settings_key: str, field: str, labels: list[str]) -> str:
    """Message for a changed default that overriding spawn areas ignore."""
    return (
        f"{settings_key} changes the default of {field}; spawn areas that "
        f"override it keep their value: {', '.join(labels)}"
    )


def _format_bound(bound: Bound, lo: float | None) -> str:
    left = "(" if bound.lo_open else "["
    right = ")" if bound.hi_open else "]"
    lo_text = "-inf" if lo is None else f"{lo:g}"
    hi_text = "inf" if bound.hi is None else f"{bound.hi:g}"
    return f"{left}{lo_text}, {hi_text}{right}"


def _bound_problem(value, bound: Bound, lo: float | None) -> str | None:
    """Return why ``value`` breaks ``bound`` (lower edge ``lo``), or ``None``."""
    if not _is_number(value) or not math.isfinite(value):
        return f"needs a finite number, got {value!r}, for"
    too_low = lo is not None and (value <= lo if bound.lo_open else value < lo)
    too_high = bound.hi is not None and (
        value >= bound.hi if bound.hi_open else value > bound.hi
    )
    if too_low or too_high:
        return f"value {value!r} is outside {_format_bound(bound, lo)} for"
    return None


def _check_model_fields(model, fields, fail) -> None:
    if not isinstance(fields, dict):
        raise fail(f"{model} overrides must map field names to numbers")
    for field, value in fields.items():
        if field in _EXCLUDED_FIELDS:
            raise fail(f'{model} cannot override "{field}"')
        if not _is_number(value):
            raise fail(f'{model} needs a number, got {value!r}, for "{field}"')


def _check_map_shape(overrides, fail) -> None:
    """Checks 1 and 2: a dict of dicts of numbers, without excluded fields."""
    if not isinstance(overrides, dict):
        raise fail(f"{OVERRIDES_KEY} must map model names to fields")
    for model, fields in overrides.items():
        _check_model_fields(model, fields, fail)


def _check_known_fields(overrides: dict, model_type: str, fail) -> None:
    """Check 3: the active model's overrides name only its per-agent fields."""
    known = PER_AGENT_FIELDS.get(model_type, {})
    for field in overrides.get(model_type) or {}:
        if field not in known:
            raise fail(f'{model_type} has no per-agent field "{field}"')


def _lower_edge(agent, model_type: str, field: str, bound: Bound) -> float | None:
    """Lower edge of ``field``; GCFM ``b_max`` uses the effective ``b_min``."""
    if model_type != "GeneralizedCentrifugalForceModel" or field != "b_max":
        return bound.lo
    b_min = getattr(agent, "b_min", None)
    return b_min if _is_number(b_min) else None


def _inherited_setting(model_type: str, field: str, global_params) -> str:
    """Settings key ``field`` inherits from: the first one set, else the first."""
    keys = PER_AGENT_FIELDS[model_type][field][0]
    is_set = (key for key in keys if getattr(global_params, key, None) is not None)
    return next(is_set, keys[0])


def _inherited_note(model_type, field, overridden, global_params, prefix="") -> str:
    if field in overridden:
        return ""
    key = _inherited_setting(model_type, field, global_params)
    return f' ({prefix}inherited from setting "{key}")'


def _is_cross_field(model_type: str, field: str, value, lo, bound: Bound) -> bool:
    """GCFM ``b_max`` fails against the effective ``b_min``, not its own bound."""
    if lo is None or lo == bound.lo:
        return False
    return model_type == "GeneralizedCentrifugalForceModel" and value < lo


def _failure_note(agent, model_type, field, overridden, global_params, bound) -> str:
    """Name the inherited settings behind a failing field."""
    note = _inherited_note(model_type, field, overridden, global_params)
    value = getattr(agent, field)
    lo = _lower_edge(agent, model_type, field, bound)
    if _is_number(value) and _is_cross_field(model_type, field, value, lo, bound):
        note += _inherited_note(model_type, "b_min", overridden, global_params, "b_min ")
    return note


def _check_effective_values(agent, model_type: str, fail, overridden, global_params) -> None:
    """Check 4: every resolved per-agent field lies within its bounds."""
    bounds = FIELD_BOUNDS.get(model_type, {})
    for field in PER_AGENT_FIELDS.get(model_type, {}):
        if not hasattr(agent, field):
            continue
        bound = bounds[field]
        lo = _lower_edge(agent, model_type, field, bound)
        problem = _bound_problem(getattr(agent, field), bound, lo)
        if problem:
            note = _failure_note(agent, model_type, field, overridden, global_params, bound)
            raise fail(f'{model_type} {problem} "{field}"{note}')


def _validate_area(key, entry: dict, model_type: str, global_params) -> None:
    from .simulation_init import create_agent_parameters

    def fail(problem):
        label = _area_label(key, entry)
        return AgentParameterError(f'spawn area {key} "{label}": {problem}')

    params = _area_params(entry)
    overrides = params.get(OVERRIDES_KEY)
    if overrides is not None:
        _check_map_shape(overrides, fail)
        _check_known_fields(overrides, model_type, fail)
    agent = create_agent_parameters(model_type, (0.0, 0.0), params, global_params)
    overridden = active_overrides(params, model_type)
    _check_effective_values(agent, model_type, fail, overridden, global_params)


def validate_agent_parameters(data: dict, model_type: str, global_params) -> None:
    """Reject invalid agent parameters of every spawn area before placement.

    Covers explicit overrides and inherited settings alike, because each
    per-agent field is resolved and its effective value is bounds-checked.
    Raises :class:`AgentParameterError` naming the area, model and field.
    """
    for key, entry in (data.get("distributions") or {}).items():
        _validate_area(key, entry, model_type, global_params)
