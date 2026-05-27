"""Regression test for issue #52 / PR #51.

Locks in the placement-spacing fix: the removed ``mean + 3*std`` safety
margin in ``_get_max_agent_radius`` previously caused the bundled
quickstart to fail with ``AgentNumberError`` at every seed. This test
ensures the canonical quickstart at the authored seed (420) places all
agents and runs to completion.
"""

from pathlib import Path

from jupedsim_scenarios import load_scenario, run_scenario

QUICKSTART = Path(__file__).resolve().parents[1] / "examples" / "assets" / "quickstart.zip"


def test_quickstart_places_all_agents_at_authored_seed():
    scenario = load_scenario(str(QUICKSTART))
    # Why: full scenario runs ~15s at max_simulation_time=300; cap to keep CI test <10s.
    scenario.max_simulation_time = 30

    result = run_scenario(scenario, seed=420)
    try:
        # Placement: all authored agents made it in (the bug rejected 1+).
        assert result.total_agents == 104
        # Simulation produced trajectory rows (ran past frame 0).
        df = result.trajectory_dataframe()
        assert len(df) > 0
    finally:
        result.cleanup()
