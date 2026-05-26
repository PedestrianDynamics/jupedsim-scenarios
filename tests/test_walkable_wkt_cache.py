"""Regression: changing walkable_area_wkt must invalidate the polygon cache,
and ``raw`` must be in sync with seed / model_type / sim_params at
serialization time.

Cache invalidation is keyed on the wkt string itself (no ``__setattr__``
hook), so direct assignment, ``.copy()`` overrides, and setters all
trigger a fresh parse. The ``raw`` mirror is rebuilt lazily by
``_synced_raw()`` immediately before serialization in ``run_scenario`` —
plain attribute assignment no longer mutates ``raw`` until then.
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
    # Cache is unset until the first .walkable_polygon access.
    assert s._walkable_polygon is None
    assert s.walkable_polygon.area == pytest.approx(1.0)
    assert s._walkable_polygon is not None


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


# --- #21: _synced_raw() mirrors seed / model_type / sim_params on demand ---

def _settings(raw: dict) -> dict:
    return raw["config"]["simulation_settings"]


def test_synced_raw_mirrors_seed():
    s = _scenario(SMALL_WKT)
    s.seed = 99
    assert _settings(s._synced_raw())["baseSeed"] == 99


def test_synced_raw_mirrors_model_type():
    s = _scenario(SMALL_WKT)
    s.model_type = "SocialForceModel"
    assert _settings(s._synced_raw())["simulationParams"]["model_type"] == "SocialForceModel"


def test_synced_raw_mirrors_sim_params_and_keeps_model_type():
    s = _scenario(SMALL_WKT)
    s.sim_params = {"max_simulation_time": 123}
    settings = _settings(s._synced_raw())
    assert settings["simulationParams"]["max_simulation_time"] == 123
    # self.model_type is the source of truth and overrides any
    # "model_type" inside sim_params.
    assert settings["simulationParams"]["model_type"] == "CollisionFreeSpeedModel"


def test_setters_still_mirror_to_raw_eagerly():
    # Setters write to both self.sim_params and raw, so callers that
    # consume raw directly (without going through _synced_raw()) see
    # setter-driven changes immediately.
    s = _scenario(SMALL_WKT)
    s.set_seed(7)
    s.set_model_type("SocialForceModel")
    s.set_max_time(45)
    assert _settings(s.raw)["baseSeed"] == 7
    assert _settings(s.raw)["simulationParams"]["model_type"] == "SocialForceModel"
    assert _settings(s.raw)["simulationParams"]["max_simulation_time"] == 45
