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


def test_piece_too_thin_to_sample_is_skipped():
    # Erodes to a non-empty strip, yet jupedsim cannot sample a first point
    # in it. The large piece still fills.
    area = shapely.union(box(0, 0, 10, 10), box(20, 0, 20.400001, 10))
    positions = _distribute_positions_until_filled(
        spawn_area=area,
        distance_to_agents=2 * RADIUS,
        distance_to_polygon=RADIUS,
        seed=1,
    )
    assert positions
    assert all(p[0] <= 10 for p in positions)


@pytest.mark.parametrize("by_number", [True, False])
def test_area_with_no_placeable_piece_raises(by_number):
    strip = box(0, 0, 0.1, 100)
    with pytest.raises(ValueError, match="wide enough"):
        if by_number:
            _distribute_positions_by_number(
                spawn_area=strip,
                number_of_agents=5,
                distance_to_agents=2 * RADIUS,
                distance_to_polygon=RADIUS,
                seed=1,
            )
        else:
            _distribute_positions_until_filled(
                spawn_area=strip,
                distance_to_agents=2 * RADIUS,
                distance_to_polygon=RADIUS,
                seed=1,
            )
