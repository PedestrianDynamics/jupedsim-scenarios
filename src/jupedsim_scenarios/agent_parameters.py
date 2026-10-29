"""Per-agent parameter fields, their settings keys, bounds and overrides.

A spawn area may carry ``agent_parameter_overrides``, shaped
``{"<model_type>": {"<jupedsim_field>": <number>}}``. Only the entry for the
active model applies; absent means the area inherits the global settings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

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
