"""Spawn areas whose clip leaves slivers too thin for one agent.

A start area that crosses an obstacle by a few centimetres splits into the
main piece plus slivers on the far side. The placer must skip pieces that
cannot hold an agent instead of failing the whole run.
"""

import pytest

pytest.importorskip("jupedsim")

import shapely  # noqa: E402
from shapely.geometry import Polygon, box  # noqa: E402

from jupedsim_scenarios.simulation_init import (  # noqa: E402
    _distribute_positions_by_number,
    _distribute_positions_until_filled,
)

RADIUS = 0.2


def _area_with_sliver():
    # 10 x 10 room; an obstacle wall at x in [9.99, 9.995] cuts a 5 mm strip
    # off the right edge, leaving a sliver no agent fits in.
    room = box(0, 0, 10, 10)
    wall = box(9.99, -1, 9.995, 11)
    area = shapely.difference(room, wall)
    assert area.geom_type == "MultiPolygon"
    return area


def test_by_number_skips_sliver():
    positions = _distribute_positions_by_number(
        spawn_area=_area_with_sliver(),
        number_of_agents=50,
        distance_to_agents=2 * RADIUS,
        distance_to_polygon=RADIUS,
        seed=1,
    )
    assert len(positions) == 50


def test_until_filled_skips_sliver():
    positions = _distribute_positions_until_filled(
        spawn_area=_area_with_sliver(),
        distance_to_agents=2 * RADIUS,
        distance_to_polygon=RADIUS,
        seed=1,
    )
    assert positions
    main = Polygon([(0, 0), (9.99, 0), (9.99, 10), (0, 10)])
    assert all(main.contains(shapely.Point(p)) for p in positions)


def test_only_sliver_places_nothing():
    sliver = box(0, 0, 0.01, 5)
    assert (
        _distribute_positions_until_filled(
            spawn_area=sliver,
            distance_to_agents=2 * RADIUS,
            distance_to_polygon=RADIUS,
            seed=1,
        )
        == []
    )
