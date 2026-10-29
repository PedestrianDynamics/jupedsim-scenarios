"""Resolved agent parameters must match the 0.7.4 baseline.

The fixture records what create_agent_parameters produced on 0.7.4 for
scenarios saved by the app (the frontend's default simulationParams) and
for no global params at all. Regenerate with
scripts/record_agent_params_baseline.py only for an intended change.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios.simulation_init import create_agent_parameters

FIXTURE = Path(__file__).parent / "fixtures" / "agent_params_baseline_0_7_4.json"
AREA_PARAMS = {"radius": 0.25, "v0": 1.3}

# Frontend default simulationParams (SimulationContext.js), verbatim.
APP_DEFAULTS = {
    "max_simulation_time": 300.0,
    "dt": None,
    "model_type": "WarpDriverModel",
    "strength_neighbor_repulsion": 2.6,
    "range_neighbor_repulsion": 0.1,
    "time_gap": 1.0,
    "gcfm_strength_neighbor_repulsion": 0.3,
    "gcfm_strength_geometry_repulsion": 0.2,
    "gcfm_max_neighbor_interaction_distance": 2.0,
    "gcfm_max_geometry_interaction_distance": 2.0,
    "gcfm_max_neighbor_repulsion_force": 9.0,
    "gcfm_max_geometry_repulsion_force": 3.0,
    "mass": 80.0,
    "tau": 0.5,
    "a_v": 1.0,
    "a_min": 0.2,
    "b_min": 0.2,
    "b_max": 0.4,
    "relaxation_time": 0.5,
    "agent_strength": 2000,
    "agent_range": 0.08,
    "sfm_obstacle_scale": 2000,
    "sfm_body_force": 120000,
    "sfm_friction": 240000,
    "T": 1.0,
    "s0": 0.5,
}

_MODELS = [
    "CollisionFreeSpeedModel",
    "CollisionFreeSpeedModelV2",
    "CollisionFreeSpeedModelV3",
    "WarpDriverModel",
    "GeneralizedCentrifugalForceModel",
    "SocialForceModel",
    "AnticipationVelocityModel",
]

BASELINE_CASES: list[tuple[str, str, dict | None]] = [
    (f"{model}-{label}", model, params)
    for model in _MODELS
    for label, params in (("none", None), ("app_defaults", APP_DEFAULTS))
] + [
    (
        "AnticipationVelocityModel-app_avm_edited",
        "AnticipationVelocityModel",
        {**APP_DEFAULTS, "T": 2.0, "s0": 0.7},
    )
]

_DROPPED = {"position", "journey_id", "stage_id"}


@pytest.mark.parametrize(
    ("case_id", "model_type", "global_params"),
    BASELINE_CASES,
    ids=[c[0] for c in BASELINE_CASES],
)
def test_resolved_agent_params_match_0_7_4_baseline(case_id, model_type, global_params):
    expected = json.loads(FIXTURE.read_text())[case_id]
    namespace = SimpleNamespace(**global_params) if global_params else None
    built = create_agent_parameters(model_type, (0.0, 0.0), dict(AREA_PARAMS), namespace)
    actual = {k: v for k, v in dataclasses.asdict(built).items() if k not in _DROPPED}

    assert actual.keys() == expected.keys()
    for field, value in expected.items():
        assert actual[field] == pytest.approx(value), field
