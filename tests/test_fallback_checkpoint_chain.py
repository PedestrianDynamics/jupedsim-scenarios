"""Unit tests for _build_fallback_checkpoint_chain (issue #8).

Pure-logic — no jupedsim import required, so this runs everywhere.
"""

from __future__ import annotations

from jupedsim_scenarios.simulation_init import _build_fallback_checkpoint_chain


def test_no_checkpoints_returns_direct_to_exit():
    """Empty checkpoint list ⇒ existing nearest-exit behavior preserved."""
    path_choices, first = _build_fallback_checkpoint_chain([], "exit_a")
    assert path_choices == {}
    assert first == "exit_a"


def test_single_checkpoint_chains_to_exit():
    path_choices, first = _build_fallback_checkpoint_chain(["cp_1"], "exit_a")
    assert first == "cp_1"
    assert path_choices == {"cp_1": [("exit_a", 100.0)]}


def test_multiple_checkpoints_chain_in_order():
    """Insertion order is the routing order — deterministic for a given JSON."""
    path_choices, first = _build_fallback_checkpoint_chain(
        ["cp_1", "cp_2", "cp_3"], "exit_a"
    )
    assert first == "cp_1"
    assert path_choices == {
        "cp_1": [("cp_2", 100.0)],
        "cp_2": [("cp_3", 100.0)],
        "cp_3": [("exit_a", 100.0)],
    }
    # Exit itself is not in path_choices — runtime ends the walk there.
    assert "exit_a" not in path_choices
