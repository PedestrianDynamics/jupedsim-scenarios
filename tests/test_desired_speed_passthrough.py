"""desired_speed* keys must survive distribution-parameter processing (#73).

The reduced param views built in ``simulation_init`` whitelist keys under
their legacy ``v0*`` names, but the public Scenario API stores the
canonical ``desired_speed*`` names (``_migrate_speed_aliases``). The
``set_agent_params`` compat mirror masked this for the mean; distributions
authored via ``add_distribution`` (or loaded from modern JSON) silently
lost mean, std, and distribution — every agent spawned at the 1.2 default
with no spread. Same bug class as #67 (strict_spawning drop). This pins
the canonical keys through ``_process_distributions`` and the sampler.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios import Scenario, run_scenario
from jupedsim_scenarios.simulation_init import (
    _process_distributions,
    _sample_agent_values,
)


def _data(params):
    return {
        "distributions": {
            "jps-distributions_0": {
                "coordinates": [[0, 0], [4, 0], [4, 4], [0, 4]],
                "parameters": {"number": 5, **params},
            }
        }
    }


def _reduced(params):
    _, dist_params = _process_distributions(_data(params))
    return dist_params["jps-distributions_0"]


def test_modern_keys_reach_reduced_view():
    reduced = _reduced(
        {
            "desired_speed": 0.6,
            "desired_speed_std": 0.3,
            "desired_speed_distribution": "gaussian",
        }
    )
    assert reduced["v0"] == 0.6
    assert reduced["v0_std"] == 0.3
    assert reduced["v0_distribution"] == "gaussian"


def test_legacy_keys_still_pass_through():
    reduced = _reduced({"v0": 0.9, "v0_std": 0.2, "v0_distribution": "gaussian"})
    assert reduced["v0"] == 0.9
    assert reduced["v0_std"] == 0.2
    assert reduced["v0_distribution"] == "gaussian"


def test_modern_keys_win_over_legacy():
    # The set_agent_params mirror writes both spellings with equal values;
    # if they ever diverge the canonical name is the source of truth.
    reduced = _reduced({"desired_speed": 0.6, "v0": 1.4})
    assert reduced["v0"] == 0.6


def test_explicit_null_does_not_shadow_legacy_keys():
    # A JSON payload may carry "desired_speed": null next to a valid
    # legacy v0 — null means "not provided", not "override with None".
    reduced = _reduced(
        {
            "desired_speed": None,
            "v0": 0.9,
            "desired_speed_std": None,
            "v0_std": 0.2,
            "desired_speed_distribution": None,
            "v0_distribution": "gaussian",
        }
    )
    assert reduced["v0"] == 0.9
    assert reduced["v0_std"] == 0.2
    assert reduced["v0_distribution"] == "gaussian"


def test_reduced_view_samples_gaussian_spread():
    reduced = _reduced(
        {
            "desired_speed": 1.0,
            "desired_speed_std": 0.3,
            "desired_speed_distribution": "gaussian",
        }
    )
    rng = np.random.RandomState(0)
    _, v0s = _sample_agent_values(reduced, 500, rng)
    v0s = np.asarray(v0s, dtype=float)
    assert float(v0s.mean()) == pytest.approx(1.0, abs=0.1)
    assert float(v0s.std()) == pytest.approx(0.3, abs=0.1)


def test_add_distribution_mean_reaches_agents_end_to_end():
    # Speed set ONLY via add_distribution (no set_agent_params mirror):
    # a slow crowd must take measurably longer than a fast one.
    def evac(desired_speed):
        s = Scenario(
            raw={},
            walkable_area_wkt="POLYGON((0 0, 20 0, 20 5, 0 5, 0 0))",
            model_type="CollisionFreeSpeedModel",
            seed=7,
            sim_params={"max_simulation_time": 120},
        )
        s.add_distribution(
            [(0.5, 0.5), (4, 0.5), (4, 4.5), (0.5, 4.5)],
            number=8,
            desired_speed=desired_speed,
        )
        s.add_exit([(19.5, 1), (20, 1), (20, 4), (19.5, 4)])
        result = run_scenario(s, seed=7)
        t = result.evacuation_time
        result.cleanup()
        return t

    slow, fast = evac(0.6), evac(1.5)
    assert slow > fast * 1.5, (slow, fast)
