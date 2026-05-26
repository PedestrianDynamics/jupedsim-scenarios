"""``Scenario.add_*`` / ``remove_*`` operations (R2.1).

Scientists who never used the web UI can extend a loaded scenario in
pure Python — adding distributions, exits, zones, and stages without
cracking open ``Scenario.raw``. The methods mirror the JSON schema so
round-trips with the web UI keep working.
"""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from jupedsim_scenarios import Scenario

SMALL_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"


def _scenario() -> Scenario:
    return Scenario(
        raw={},
        walkable_area_wkt=SMALL_WKT,
        model_type="CollisionFreeSpeedModel",
        seed=42,
        sim_params={"max_simulation_time": 60},
    )


# -- add_distribution --------------------------------------------------


def test_add_distribution_assigns_id_and_records_polygon():
    s = _scenario()
    did = s.add_distribution([(0, 0), (2, 0), (2, 2), (0, 2)], number=20)
    assert did == "jps-distributions_0"
    entry = s.distributions[did]
    assert entry["parameters"]["number"] == 20
    # Coordinates closed automatically.
    assert entry["coordinates"][0] == entry["coordinates"][-1] == [0.0, 0.0]


def test_add_distribution_accepts_shapely_polygon():
    s = _scenario()
    poly = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])
    did = s.add_distribution(poly, number=5, desired_speed=1.4)
    assert s.distributions[did]["parameters"]["desired_speed"] == 1.4


def test_add_distribution_auto_id_picks_next_free_index():
    s = _scenario()
    s.add_distribution([(0, 0), (1, 0), (1, 1)])
    s.add_distribution([(2, 2), (3, 2), (3, 3)])
    s.remove_distribution("jps-distributions_0")
    # Max existing is _1; next free is _2 (we don't recycle freed ids).
    next_id = s.add_distribution([(4, 4), (5, 4), (5, 5)])
    assert next_id == "jps-distributions_2"


def test_add_distribution_explicit_id_collision_raises():
    s = _scenario()
    s.add_distribution([(0, 0), (1, 0), (1, 1)], identifier="my-source")
    with pytest.raises(ValueError, match="already exists"):
        s.add_distribution([(2, 2), (3, 2), (3, 3)], identifier="my-source")


def test_add_distribution_unknown_kwarg_raises():
    s = _scenario()
    with pytest.raises(TypeError, match="received unknown keyword"):
        s.add_distribution([(0, 0), (1, 0), (1, 1)], radius_dist="gaussian")


def test_add_distribution_too_few_points_raises():
    s = _scenario()
    with pytest.raises(ValueError, match="at least 3"):
        s.add_distribution([(0, 0), (1, 0)])


# -- add_exit ---------------------------------------------------------


def test_add_exit_records_throttling_flag():
    s = _scenario()
    eid = s.add_exit([(8, 0), (10, 0), (10, 10), (8, 10)], max_throughput=1.5)
    assert s.exits[eid]["enable_throughput_throttling"] is True
    assert s.exits[eid]["max_throughput"] == 1.5


def test_add_exit_default_no_throttling():
    s = _scenario()
    eid = s.add_exit([(8, 0), (10, 0), (10, 10), (8, 10)])
    assert s.exits[eid]["enable_throughput_throttling"] is False


# -- add_zone + add_stage ---------------------------------------------


def test_add_zone_records_speed_factor():
    s = _scenario()
    zid = s.add_zone([(2, 2), (4, 2), (4, 4), (2, 4)], speed_factor=0.5)
    assert s.zones[zid]["speed_factor"] == 0.5


def test_add_stage_records_waiting_time():
    s = _scenario()
    sid = s.add_stage([(5, 5), (6, 5), (6, 6), (5, 6)], waiting_time=3.0)
    # raw["checkpoints"] is the JSON-schema location; Scenario.stages is
    # the runtime-vocabulary alias.
    assert s.stages[sid]["waiting_time"] == 3.0
    assert sid in s.raw["checkpoints"]


# -- remove_* ---------------------------------------------------------


def test_remove_distribution_pops_entry():
    s = _scenario()
    did = s.add_distribution([(0, 0), (1, 0), (1, 1)])
    s.remove_distribution(did)
    assert did not in s.distributions


def test_remove_unknown_raises():
    s = _scenario()
    with pytest.raises(KeyError):
        s.remove_distribution("nope")
    with pytest.raises(KeyError):
        s.remove_exit("nope")
    with pytest.raises(KeyError):
        s.remove_zone("nope")
    with pytest.raises(KeyError):
        s.remove_stage("nope")


def test_remove_exit_accepts_int_index():
    # R3.4: parity with the other remove_* methods.
    s = _scenario()
    s.add_exit([(8, 0), (10, 0), (10, 10), (8, 10)])  # index 0
    s.add_exit([(0, 8), (2, 8), (2, 10), (0, 10)])    # index 1
    assert len(s.exits) == 2
    s.remove_exit(0)
    assert len(s.exits) == 1
    # Negative / out-of-range index raises IndexError with the same
    # shape as distributions/zones/stages.
    with pytest.raises(IndexError):
        s.remove_exit(5)
