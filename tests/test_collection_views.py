"""``Scenario.exits/distributions/stages/zones`` return read-only views.

Top-level mutation (adding or removing entries via the property) raises
``TypeError`` so callers can't bypass the setters' invariants. The
nested per-element dicts are still mutable — that's the surface the
setters write through.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import Scenario

SMALL_WKT = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"


def _scenario() -> Scenario:
    return Scenario(
        raw={
            "exits": {"e0": {"coordinates": []}},
            "distributions": {"d0": {"parameters": {"number": 1}, "coordinates": []}},
            "checkpoints": {"c0": {"waiting_time": 0.0, "coordinates": []}},
            "zones": {"z0": {"speed_factor": 1.0, "coordinates": []}},
        },
        walkable_area_wkt=SMALL_WKT,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )


@pytest.mark.parametrize(
    "attr,key,payload",
    [
        ("exits", "e1", {}),
        ("distributions", "d1", {}),
        ("stages", "c1", {}),
        ("zones", "z1", {}),
    ],
)
def test_view_rejects_top_level_mutation(attr, key, payload):
    s = _scenario()
    with pytest.raises(TypeError):
        getattr(s, attr)[key] = payload


def test_nested_dicts_remain_mutable():
    s = _scenario()
    # Setters reach inside; that path must keep working.
    s.distributions["d0"]["parameters"]["number"] = 9
    assert s.raw["distributions"]["d0"]["parameters"]["number"] == 9


def test_setters_still_function():
    s = _scenario()
    s.set_agent_count("d0", 5)
    s.set_zone_speed_factor("z0", 2.0)
    s.set_checkpoint_waiting_time("c0", 3.0)
    assert s.distributions["d0"]["parameters"]["number"] == 5
    assert s.zones["z0"]["speed_factor"] == 2.0
    assert s.stages["c0"]["waiting_time"] == 3.0
