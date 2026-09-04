"""Start-area capacity rule shared with the web app.

The app refuses to place more agents in a start area than the area can
hold; the library applies the same rule before scaling a scenario so a
count that would silently turn into deferred spawns is rejected up front.

    max_agents = floor(walkable_area / (pi * radius**2) * PRACTICAL_PACKING_FACTOR)

``walkable_area`` is the distribution polygon minus the obstacles (the
holes of the walkable area), in square metres. ``radius`` is the
distribution's ``parameters.radius`` (default 0.2 m).

This module is the single owner of :data:`PRACTICAL_PACKING_FACTOR`. The
frontend (``DistributionEditorModal.js``) mirrors the constant and points
back here; change both together.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from shapely.geometry import Polygon
from shapely.ops import unary_union

if TYPE_CHECKING:
    from .runner import Scenario

PRACTICAL_PACKING_FACTOR = 0.5
DEFAULT_AGENT_RADIUS = 0.2


def distribution_walkable_area(scenario: Scenario, dist_id: str) -> float:
    """Area in square metres of the distribution polygon minus obstacles."""
    dist = scenario.distributions[dist_id]
    polygon = Polygon(dist.get("coordinates", []))
    if polygon.is_empty:
        return 0.0
    holes = [Polygon(interior) for interior in scenario.walkable_polygon.interiors]
    if not holes:
        return float(polygon.area)
    return float(polygon.difference(unary_union(holes)).area)


def max_agents_for_distribution(scenario: Scenario, dist_id: str) -> int:
    """Largest agent count the start area ``dist_id`` accepts under the app's rule."""
    params = scenario.distributions[dist_id].get("parameters", {})
    radius = float(params.get("radius", DEFAULT_AGENT_RADIUS) or DEFAULT_AGENT_RADIUS)
    area = distribution_walkable_area(scenario, dist_id)
    theoretical = area / (math.pi * radius * radius)
    return max(0, math.floor(theoretical * PRACTICAL_PACKING_FACTOR))
