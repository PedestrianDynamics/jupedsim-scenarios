"""Every registered model builder must construct against the installed jupedsim.

CollisionFreeSpeedModelV2 crashed with TypeError on every run: the builder
passed strength/range_neighbor_repulsion, but the upstream V2 operational
model takes no constructor args — those params are per-agent
(CollisionFreeSpeedModelV2AgentParameters, populated in simulation_init).
Constructing each builder with defaults and with all known model-param
keys pins the registry against upstream signature drift.
"""

from __future__ import annotations

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios import Scenario, run_scenario
from jupedsim_scenarios.runner import _MODEL_BUILDERS, _MODEL_PARAM_KEYS, _build_model

_FULL_PARAMS = dict.fromkeys(_MODEL_PARAM_KEYS, 0.5)


@pytest.mark.parametrize("model_type", sorted(_MODEL_BUILDERS))
def test_builder_constructs_with_defaults(model_type):
    assert _build_model(model_type, {}) is not None


@pytest.mark.parametrize("model_type", sorted(_MODEL_BUILDERS))
def test_builder_constructs_with_all_known_param_keys(model_type):
    # Builders read from sim_params by allow-listed key; unknown-to-them
    # keys must be ignored, known ones accepted by the upstream constructor.
    assert _build_model(model_type, dict(_FULL_PARAMS)) is not None


def test_v2_scenario_runs_end_to_end():
    s = Scenario(
        raw={},
        walkable_area_wkt="POLYGON((0 0, 12 0, 12 4, 0 4, 0 0))",
        model_type="CollisionFreeSpeedModelV2",
        seed=3,
        sim_params={"max_simulation_time": 60},
    )
    s.add_distribution([(0.5, 0.5), (3, 0.5), (3, 3.5), (0.5, 3.5)], number=6)
    s.add_exit([(11.5, 1), (12, 1), (12, 3), (11.5, 3)])
    result = run_scenario(s, seed=3)
    assert result.success
    result.cleanup()
