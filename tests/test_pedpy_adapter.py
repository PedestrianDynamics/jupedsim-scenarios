"""``ScenarioResult.as_pedpy_trajectory()`` adapter (R2.6).

Thin wrapper around the trajectory dataframe + frame rate, returning a
``pedpy.TrajectoryData`` so callers can pass it straight into pedpy's
analysis functions.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import run_scenario


def test_as_pedpy_trajectory_returns_pedpy_object(corridor_scenario):
    pedpy = pytest.importorskip("pedpy")
    result = run_scenario(corridor_scenario, seed=42)
    try:
        traj = result.as_pedpy_trajectory()
        assert isinstance(traj, pedpy.TrajectoryData)
        # The frame rate threads through from the run.
        assert traj.frame_rate == result.frame_rate
        # Schema: pedpy requires id, frame, x, y. The data attribute
        # also exposes a 'point' column populated by pedpy itself.
        for column in ("id", "frame", "x", "y"):
            assert column in traj.data.columns
        # At least one agent's worth of data made it through.
        assert len(traj.data) > 0
    finally:
        result.cleanup()


def test_as_pedpy_trajectory_raises_without_sqlite(corridor_scenario):
    pytest.importorskip("pedpy")
    result = run_scenario(corridor_scenario, seed=42)
    result.cleanup()  # deletes the sqlite file
    with pytest.raises(FileNotFoundError):
        result.as_pedpy_trajectory()
