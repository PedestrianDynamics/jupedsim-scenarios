"""``Scenario.copy()`` independence.

``copy()`` returns a deep copy of the scenario. The clone shares no
mutable state with the original — used by ``run_sweep`` to isolate
per-trial scenarios. Field overrides via ``copy(seed=..., ...)`` are
NOT supported; copy first, then mutate the clone (the setter / direct
attribute assignment path is the single canonical mutation surface).
"""

from __future__ import annotations

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


def test_copy_returns_independent_scenario():
    s = _scenario()
    clone = s.copy()
    # Mutating the clone doesn't bleed into the original.
    clone.sim_params["max_simulation_time"] = 999
    clone.seed = 7
    clone.model_type = "SocialForceModel"
    assert s.sim_params["max_simulation_time"] == 60
    assert s.seed == 42
    assert s.model_type == "CollisionFreeSpeedModel"


def test_copy_then_assign_is_the_canonical_field_change_pattern():
    s = _scenario()
    clone = s.copy()
    clone.seed = 99
    clone.max_simulation_time = 120
    assert clone.seed == 99
    assert clone.max_simulation_time == 120
    assert s.seed == 42
    assert s.max_simulation_time == 60


def test_copy_clones_raw_deeply():
    # raw is a nested dict; the deep copy must give the clone its own
    # nested mutable state so add_distribution etc. don't reach back.
    s = _scenario()
    s.raw["distributions"] = {"d0": {"parameters": {"number": 10}}}
    clone = s.copy()
    clone.raw["distributions"]["d0"]["parameters"]["number"] = 99
    assert s.raw["distributions"]["d0"]["parameters"]["number"] == 10
