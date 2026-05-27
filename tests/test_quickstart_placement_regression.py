"""Regression tests for the bundled quickstart scenario.

The first test guards the placement-spacing fix from PR #51
(commit 582ffb9). The second flags the open evacuation-parity bug
with the Web-Based JuPedSim editor as an ``xfail(strict=True)`` so
the divergence is visible in pytest output and forces a marker
removal once the bug is fixed.
"""

from pathlib import Path

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios import load_scenario, run_scenario  # noqa: E402

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


@pytest.mark.xfail(
    strict=True,
    reason="lib evacuates 97/104 where the editor evacuates 104/104 — see #59",
)
def test_quickstart_fully_evacuates_at_authored_seed():
    """Editor parity: the editor runs this scenario to completion
    (all 104 agents evacuate). The library currently strands 7 agents
    in the corridor band; xfail-strict here surfaces the bug in CI
    and will turn red — forcing removal of this marker — once parity
    is restored.
    """
    scenario = load_scenario(str(QUICKSTART))
    result = run_scenario(scenario, seed=420)
    try:
        assert result.success is True
        assert result.agents_evacuated == result.total_agents
        assert result.agents_remaining == 0
    finally:
        result.cleanup()
