"""The runtime stage-target picker must use the same clearance floor as
``_pick_initial_stage_target``: ``reach_penetration`` is included, so the
first hop and every later hop sample the same region of a waiting stage
(#80)."""

from __future__ import annotations

from shapely.geometry import Polygon

from jupedsim_scenarios import direct_steering_runtime as dsr

WAITING_CFG = {
    "polygon": Polygon([(0, 0), (4, 0), (4, 4), (0, 4)]),
    "waiting_time": 5.0,
    "stage_type": "checkpoint",
}


def _captured_clearance(monkeypatch, wait_state):
    captured = {}

    def fake_random_point(polygon, rng, min_clearance=0.2):
        captured["min_clearance"] = min_clearance
        return (1.0, 1.0)

    monkeypatch.setattr(dsr, "random_point_in_polygon", fake_random_point)
    dsr.pick_stage_target(wait_state, WAITING_CFG)
    return captured["min_clearance"]


def test_runtime_clearance_includes_reach_penetration(monkeypatch):
    wait_state = {
        "base_seed": 1,
        "step_index": 0,
        "agent_radius": 0.2,
        "reach_penetration": 0.25,
    }
    assert _captured_clearance(monkeypatch, wait_state) == 0.25


def test_large_radius_still_wins_over_reach_penetration(monkeypatch):
    wait_state = {
        "base_seed": 1,
        "step_index": 0,
        "agent_radius": 0.5,
        "reach_penetration": 0.25,
    }
    assert _captured_clearance(monkeypatch, wait_state) == 0.5 * 0.8
