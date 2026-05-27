"""Placement-failure errors must reference the user's distribution id
(e.g. ``jps-distributions_0``), not an opaque enumerate index.

Pre-fix the error read::

    CRITICAL: Failed to place agents in distribution area 0. ...

Downstream tools (the Web editor labels its start areas "Start 1",
"Start 2", ...) could not map "distribution area 0" back to a specific
geometry — both because the index was zero-based against a one-based UI
*and* because it was the internal enumerate position rather than the
stable ``jps-distributions_N`` key. This test pins the dist_id in the
error so future refactors of the spawn loop can't silently regress to
the opaque index.
"""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def overcrowded_scenario():
    """Same geometry as the corridor fixture, but the start area is asked
    to hold ten thousand agents — guaranteed to fail at placement."""
    pytest.importorskip("jupedsim")
    from jupedsim_scenarios import Scenario

    data = json.loads((FIXTURES / "corridor_simple.json").read_text())
    data["distributions"]["jps-distributions_0"]["parameters"]["number"] = 10000
    sim_params = data["config"]["simulation_settings"]["simulationParams"]
    return Scenario(
        raw=data,
        walkable_area_wkt=data["walkable_area_wkt"],
        model_type=sim_params["model_type"],
        seed=data["seed"],
        sim_params=dict(sim_params),
        source_path=str(FIXTURES / "corridor_simple.json"),
    )


def test_placement_failure_names_the_distribution_id(overcrowded_scenario):
    from jupedsim_scenarios import run_scenario

    with pytest.raises(Exception) as exc_info:
        result = run_scenario(overcrowded_scenario, seed=42)
        result.cleanup()  # only reached if run somehow succeeded

    msg = str(exc_info.value)
    assert "jps-distributions_0" in msg, (
        "placement-failure error lost the distribution id; users can no "
        "longer trace the failure back to a specific start area. "
        f"Got: {msg!r}"
    )
    # Guard against future regressions where the id is added *and* the
    # opaque integer index is left behind unquoted.
    assert "distribution area 0" not in msg, (
        f"error still references opaque enumerate index. Got: {msg!r}"
    )
