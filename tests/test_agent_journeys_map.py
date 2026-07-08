"""``spawning_info["agent_journeys"]`` — per-agent journey attribution.

The trajectory only records positions, so the journey each agent was assigned
at spawn (the weighted draw across a distribution's ``journey_weights``) is
otherwise unrecoverable downstream. ``_add_agents`` records it into
``spawning_info`` so consumers can colour dots / count by the actual journey.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import ScenarioRunner


def test_agent_journeys_maps_every_spawned_agent(corridor_scenario):
    """corridor_simple has one journey (``j_corridor``, weight 100) on its one
    distribution, so every init-spawned agent maps to that journey id."""
    pytest.importorskip("jupedsim")
    with ScenarioRunner(corridor_scenario, seed=42) as runner:
        agent_journeys = runner._spawning_info["agent_journeys"]

        # Present and non-empty for a journey-based scenario.
        assert agent_journeys, "agent_journeys should not be empty"
        # Every agent on the single 100%-weighted journey maps to its v2 id.
        assert set(agent_journeys.values()) == {"j_corridor"}
        # Keys are the JuPedSim integer agent ids.
        assert all(isinstance(aid, int) for aid in agent_journeys)
        # One entry per spawned agent (before any stepping/flow spawning).
        assert len(agent_journeys) == runner.agent_count
