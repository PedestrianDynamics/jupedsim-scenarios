"""Guard the public aliases promoted in jupedsim-scenarios#4.

If anyone ever renames or removes one of the underscored helpers,
this test fails — pointing them at the consumers (the web app's
`simulation_service` and several of its test files) that import the
public names.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "public_name, private_name",
    [
        ("random_point_in_polygon", "_random_point_in_polygon"),
        ("find_nearest_exit", "_find_nearest_exit"),
        ("sample_agent_values", "_sample_agent_values"),
        ("clip_exit_to_walkable", "_clip_exit_to_walkable"),
    ],
)
def test_public_alias_matches_private_helper(public_name, private_name):
    pytest.importorskip("jupedsim")
    import jupedsim_scenarios.simulation_init as sim_init

    assert getattr(sim_init, public_name) is getattr(sim_init, private_name)
