"""Tests for the legacy `journeys`+`transitions` → `journeys_v2` shim (#13).

Pure-logic — the helper rewrites a dict in place; no jupedsim needed.
"""

from __future__ import annotations

from jupedsim_scenarios.simulation_init import _migrate_legacy_journeys_to_v2


def test_no_op_when_journeys_v2_already_present():
    data = {
        "journeys": [{"id": "j0", "stages": ["exit_0"]}],
        "journeys_v2": [{"id": "v2", "sequence": ["exit_0"]}],
        "distributions": {"dist_0": {}},
    }
    _migrate_legacy_journeys_to_v2(data)
    assert data["journeys_v2"] == [{"id": "v2", "sequence": ["exit_0"]}]
    assert "journey_weights" not in data["distributions"]["dist_0"]


def test_no_op_when_no_legacy_journeys():
    data = {"distributions": {"dist_0": {}}}
    _migrate_legacy_journeys_to_v2(data)
    assert "journeys_v2" not in data
    assert "journey_weights" not in data["distributions"]["dist_0"]


def test_single_journey_assigns_all_distributions():
    """RiMEA 07 / 13 pattern: one journey, no distributions in stages →
    every distribution feeds it."""
    data = {
        "journeys": [{"id": "j0", "stages": ["exit_0"]}],
        "distributions": {"dist_a": {}, "dist_b": {}, "dist_c": {}},
    }
    _migrate_legacy_journeys_to_v2(data)
    assert data["journeys_v2"] == [
        {"id": "j0", "name": "j0", "color": "#888888", "sequence": ["exit_0"]}
    ]
    for dk in ("dist_a", "dist_b", "dist_c"):
        assert data["distributions"][dk]["journey_weights"] == [
            {"journey_id": "j0", "weight": 100.0}
        ]


def test_distribution_appears_in_stages_becomes_feeder():
    """vv_helpers default: `journeys[i].stages = [dist_i, exit_(i%n)]`.
    The distribution stage is stripped from sequence and recorded as a
    feeder via journey_weights instead."""
    data = {
        "journeys": [
            {"id": "j0", "stages": ["dist_0", "exit_0"]},
            {"id": "j1", "stages": ["dist_1", "exit_1"]},
        ],
        "distributions": {"dist_0": {}, "dist_1": {}},
    }
    _migrate_legacy_journeys_to_v2(data)
    seqs = {j["id"]: j["sequence"] for j in data["journeys_v2"]}
    assert seqs == {"j0": ["exit_0"], "j1": ["exit_1"]}
    assert data["distributions"]["dist_0"]["journey_weights"] == [
        {"journey_id": "j0", "weight": 100.0}
    ]
    assert data["distributions"]["dist_1"]["journey_weights"] == [
        {"journey_id": "j1", "weight": 100.0}
    ]


def test_checkpoint_in_middle_preserved_in_sequence():
    data = {
        "journeys": [
            {"id": "j0", "stages": ["dist_0", "checkpoint_0", "exit_0"]},
        ],
        "distributions": {"dist_0": {}},
    }
    _migrate_legacy_journeys_to_v2(data)
    assert data["journeys_v2"][0]["sequence"] == ["checkpoint_0", "exit_0"]
    assert data["distributions"]["dist_0"]["journey_weights"] == [
        {"journey_id": "j0", "weight": 100.0}
    ]


def test_transitions_pick_up_distribution_to_journey_edges():
    """When `journeys[i].stages` doesn't list the distribution, the
    `transitions` array still tells us who feeds whom."""
    data = {
        "journeys": [
            {"id": "j0", "stages": ["exit_0"]},
            {"id": "j1", "stages": ["exit_1"]},
        ],
        "transitions": [
            {"from": "dist_0", "to": "exit_0", "journey_id": "j0"},
            {"from": "dist_1", "to": "exit_1", "journey_id": "j1"},
        ],
        "distributions": {"dist_0": {}, "dist_1": {}},
    }
    _migrate_legacy_journeys_to_v2(data)
    assert data["distributions"]["dist_0"]["journey_weights"] == [
        {"journey_id": "j0", "weight": 100.0}
    ]
    assert data["distributions"]["dist_1"]["journey_weights"] == [
        {"journey_id": "j1", "weight": 100.0}
    ]


def test_distribution_feeding_multiple_journeys_splits_evenly():
    data = {
        "journeys": [
            {"id": "j_short", "stages": ["dist_0", "exit_0"]},
            {"id": "j_long", "stages": ["dist_0", "checkpoint_0", "exit_0"]},
        ],
        "distributions": {"dist_0": {}},
    }
    _migrate_legacy_journeys_to_v2(data)
    weights = data["distributions"]["dist_0"]["journey_weights"]
    assert sorted(weights, key=lambda w: w["journey_id"]) == [
        {"journey_id": "j_long", "weight": 50.0},
        {"journey_id": "j_short", "weight": 50.0},
    ]


def test_journey_with_empty_sequence_is_dropped():
    """A legacy journey whose stages are all distributions (no targets)
    can't be migrated — skip it instead of creating an empty-sequence v2
    entry that would crash _create_journeys_v2."""
    data = {
        "journeys": [{"id": "j0", "stages": ["dist_0"]}],
        "distributions": {"dist_0": {}},
    }
    _migrate_legacy_journeys_to_v2(data)
    assert "journeys_v2" not in data
