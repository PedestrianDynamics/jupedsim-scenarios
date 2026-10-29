"""``create_agent_parameters`` falls back to the ``PER_AGENT_FIELDS`` defaults.

The function hardcodes its fallbacks; this pins them to the table so the two
cannot drift apart.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("jupedsim")

from jupedsim_scenarios.agent_parameters import PER_AGENT_FIELDS
from jupedsim_scenarios.simulation_init import create_agent_parameters

CASES = [
    pytest.param(model, field, fallback, id=f"{model}-{field}")
    for model, fields in PER_AGENT_FIELDS.items()
    for field, (_keys, fallback) in fields.items()
]


@pytest.mark.parametrize(("model", "field", "fallback"), CASES)
def test_unset_settings_resolve_to_table_fallback(model, field, fallback):
    agent = create_agent_parameters(model, (0.0, 0.0), {}, SimpleNamespace())
    assert getattr(agent, field) == pytest.approx(fallback)


def test_v2_without_settings_keeps_jupedsim_defaults():
    # Known exception: with no settings object at all, V2 leaves the
    # neighbor repulsion to JuPedSim's own defaults, not the table's 2.6.
    agent = create_agent_parameters(
        "CollisionFreeSpeedModelV2", (0.0, 0.0), {}, None
    )
    assert agent.strength_neighbor_repulsion == pytest.approx(8.0)
    assert agent.range_neighbor_repulsion == pytest.approx(0.1)
