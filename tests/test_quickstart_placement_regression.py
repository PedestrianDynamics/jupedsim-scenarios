"""Regression tests for the bundled quickstart scenario.

The first test guards the placement-spacing fix from PR #51
(commit 582ffb9): no ``AgentNumberError`` at the authored seed.
The second guards editor parity end-to-end: all 104 agents evacuate
within the authored ``max_simulation_time``, matching the Web-Based
JuPedSim editor's recorded run.
"""

from pathlib import Path

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios import load_scenario, run_scenario  # noqa: E402

QUICKSTART = Path(__file__).resolve().parents[1] / "examples" / "assets" / "quickstart.zip"


def test_quickstart_places_all_agents_at_authored_seed():
    scenario = load_scenario(str(QUICKSTART))
    # Why: full scenario runs ~5s; cap to keep CI test bounded even on slow runners.
    scenario.max_simulation_time = 60

    result = run_scenario(scenario, seed=420)
    try:
        # Placement: all authored agents made it in (the bug rejected 1+).
        assert result.total_agents == 104
        # Simulation produced trajectory rows (ran past frame 0).
        df = result.trajectory_dataframe()
        assert len(df) > 0
    finally:
        result.cleanup()


def test_quickstart_fully_evacuates_at_authored_seed():
    scenario = load_scenario(str(QUICKSTART))
    result = run_scenario(scenario, seed=420)
    try:
        assert result.success is True
        assert result.agents_evacuated == result.total_agents == 104
        assert result.agents_remaining == 0
    finally:
        result.cleanup()
