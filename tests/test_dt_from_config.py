"""``dt`` falls back to ``simulationParams.dt`` when the argument is None."""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from jupedsim_scenarios import load_scenario, run_scenario

FIXTURE = pathlib.Path(__file__).parent / "golden" / "fixtures" / "warpdrivermodel"


def test_dt_from_config_is_used(tmp_path):
    pytest.importorskip("jupedsim")
    scenario = load_scenario(str(FIXTURE))
    assert scenario.sim_params["dt"] == 0.05
    out = tmp_path / "wd.sqlite"
    result = run_scenario(scenario, seed=1, every_nth_frame=10, output_path=out)
    assert result.dt == pytest.approx(0.05)
    assert result.frame_rate == pytest.approx(2.0)
    con = sqlite3.connect(out)
    try:
        fps = con.execute("SELECT value FROM metadata WHERE key = 'fps'").fetchone()
    finally:
        con.close()
    assert fps is not None
    assert float(fps[0]) == pytest.approx(2.0)


def test_explicit_dt_overrides_config():
    pytest.importorskip("jupedsim")
    scenario = load_scenario(str(FIXTURE))
    scenario.max_simulation_time = 1
    result = run_scenario(scenario, seed=1, dt=0.02)
    try:
        assert result.dt == pytest.approx(0.02)
    finally:
        result.cleanup()


def test_invalid_config_dt_raises():
    pytest.importorskip("jupedsim")
    scenario = load_scenario(str(FIXTURE))
    scenario.sim_params["dt"] = -1
    with pytest.raises(ValueError, match="dt"):
        run_scenario(scenario, seed=1)
