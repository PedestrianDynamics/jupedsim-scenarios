"""``Scenario.plot(show_journeys=...)`` journey overlay.

Journeys are drawn as curved arrows connecting the centroids of the elements
in each journey's stage sequence.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import load_scenario, run_scenario

JOURNEY_SCENARIO = "examples/cookbook/scenario_files/stage-routing-square-room"
# Newer web-editor export: routes live under ``journeys_v2`` (key ``sequence``)
# while the legacy ``journeys`` array is empty.
JOURNEY_V2_SCENARIO = "examples/assets/scenario.zip"


def _arrow_count(ax):
    from matplotlib.text import Annotation

    return sum(
        isinstance(t, Annotation) and t.arrow_patch is not None
        for t in ax.texts
    )


def test_plot_draws_journey_arrows():
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")

    scenario = load_scenario(JOURNEY_SCENARIO)
    # One journey of four stages -> three connecting arrows.
    assert len(scenario.journeys) == 1
    ax = scenario.plot()
    assert _arrow_count(ax) == 3
    legend_labels = {t.get_text() for t in ax.get_legend().get_texts()}
    assert "Journey" in legend_labels


def test_plot_draws_journeys_v2_arrows():
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")

    scenario = load_scenario(JOURNEY_V2_SCENARIO)
    # Legacy `journeys` is empty here; routes come from `journeys_v2`.
    assert scenario.journeys == []
    ax = scenario.plot()
    assert _arrow_count(ax) > 0
    legend_labels = {t.get_text() for t in ax.get_legend().get_texts()}
    assert "Journey" in legend_labels


def test_plot_show_journeys_false_draws_no_arrows():
    matplotlib = pytest.importorskip("matplotlib")
    matplotlib.use("Agg")

    scenario = load_scenario(JOURNEY_SCENARIO)
    ax = scenario.plot(show_journeys=False)
    assert _arrow_count(ax) == 0
    legend_labels = {t.get_text() for t in ax.get_legend().get_texts()}
    assert "Journey" not in legend_labels


def test_plot_overlays_trajectories():
    pytest.importorskip("matplotlib").use("Agg")
    pytest.importorskip("pedpy")

    scenario = load_scenario(JOURNEY_SCENARIO)
    result = run_scenario(scenario, seed=42)
    try:
        ax_plain = scenario.plot()
        # Passing trajectories alone draws the overlay (no flag needed).
        ax_traj = scenario.plot(trajectories=result)
        assert len(ax_traj.get_lines()) > len(ax_plain.get_lines())
        # Explicit suppression wins even when data is given.
        ax_off = scenario.plot(trajectories=result, show_trajectories=False)
        assert len(ax_off.get_lines()) == len(ax_plain.get_lines())
    finally:
        result.cleanup()


def test_plot_show_trajectories_requires_data():
    pytest.importorskip("matplotlib").use("Agg")

    scenario = load_scenario(JOURNEY_SCENARIO)
    with pytest.raises(ValueError):
        scenario.plot(show_trajectories=True)
