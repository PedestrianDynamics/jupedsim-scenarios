"""``ScenarioResult.visualise()`` — interactive plotly playback of a run.

Builds a plotly Figure with one animation frame per trajectory frame, a play
button, and a time slider; optionally writes a self-contained HTML file.
"""

from __future__ import annotations

import pytest

from jupedsim_scenarios import run_scenario


def test_visualise_returns_figure_with_frames(corridor_scenario):
    go = pytest.importorskip("plotly.graph_objects")
    from jupedsim_scenarios.runner import _TARGET_ANIMATION_FRAMES

    result = run_scenario(corridor_scenario, seed=42)
    try:
        fig = result.visualise(every_nth_frame=5)
        assert isinstance(fig, go.Figure)
        # Animation frames plus a slider and play/pause controls.
        assert len(fig.frames) > 0
        assert fig.layout.sliders
        assert fig.layout.updatemenus
        # Auto stride keeps the frame count near the target cap.
        auto = result.visualise()
        assert len(auto.frames) <= _TARGET_ANIMATION_FRAMES
    finally:
        result.cleanup()


def test_visualise_rejects_bad_every_nth_frame(corridor_scenario):
    pytest.importorskip("plotly.graph_objects")

    result = run_scenario(corridor_scenario, seed=42)
    try:
        with pytest.raises(ValueError):
            result.visualise(every_nth_frame=0)
    finally:
        result.cleanup()


def test_visualise_saves_html(corridor_scenario, tmp_path):
    pytest.importorskip("plotly.graph_objects")

    result = run_scenario(corridor_scenario, seed=42)
    try:
        out = tmp_path / "run.html"
        result.visualise(save_path=out, every_nth_frame=5)
        assert out.exists()
        assert out.stat().st_size > 0
    finally:
        result.cleanup()


def test_visualise_raises_without_sqlite(corridor_scenario):
    pytest.importorskip("plotly.graph_objects")

    result = run_scenario(corridor_scenario, seed=42)
    result.cleanup()  # deletes the sqlite file
    with pytest.raises(FileNotFoundError):
        result.visualise()
