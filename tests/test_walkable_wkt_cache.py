"""Regression: changing walkable_area_wkt must invalidate the polygon cache.

Before #18 was fixed, plain field assignment
(``scenario.walkable_area_wkt = new_wkt``) left the cached
``_walkable_polygon`` stale; only ``.copy(walkable_area_wkt=...)``
refreshed it. The simulator reads the cached polygon, so sweeps that
mutated the field directly silently ran every trial on the original
geometry.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import Scenario

SMALL_WKT = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"      # area = 1
LARGE_WKT = "POLYGON((0 0, 5 0, 5 5, 0 5, 0 0))"      # area = 25


def _scenario(wkt: str) -> Scenario:
    return Scenario(
        raw={},
        walkable_area_wkt=wkt,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )


def test_constructor_parses_polygon_lazily():
    s = _scenario(SMALL_WKT)
    assert s.walkable_polygon.area == pytest.approx(1.0)


def test_field_assignment_invalidates_cache():
    s = _scenario(SMALL_WKT)
    _ = s.walkable_polygon                   # prime the cache
    s.walkable_area_wkt = LARGE_WKT
    assert s.walkable_polygon.area == pytest.approx(25.0)


def test_copy_override_invalidates_cache():
    s = _scenario(SMALL_WKT)
    _ = s.walkable_polygon
    clone = s.copy(walkable_area_wkt=LARGE_WKT)
    assert clone.walkable_polygon.area == pytest.approx(25.0)
    # Original is unchanged.
    assert s.walkable_polygon.area == pytest.approx(1.0)
