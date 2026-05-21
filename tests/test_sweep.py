"""Tests for run_sweep.

Split into:
- Pure-logic tests that don't need jupedsim (cartesian product, validation,
  dataframe shape with stub trials).
- One end-to-end test that does need jupedsim — gated with importorskip.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from jupedsim_scenarios.runner import ScenarioResult
from jupedsim_scenarios.sweep import (
    SweepResult,
    Trial,
    _iter_axis_combinations,
    _validate_axes,
    run_sweep,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# --- pure-logic ------------------------------------------------------------


def test_cartesian_product_order():
    combos = list(
        _iter_axis_combinations({"a": [1, 2], "b": ["x", "y", "z"]})
    )
    assert len(combos) == 6
    # Inner axis ("b") varies fastest.
    assert combos[:3] == [
        {"a": 1, "b": "x"},
        {"a": 1, "b": "y"},
        {"a": 1, "b": "z"},
    ]


def test_empty_axes_yields_one_empty_combo():
    combos = list(_iter_axis_combinations({}))
    assert combos == [{}]


def test_validate_axes_rejects_missing_apply():
    with pytest.raises(ValueError, match="without an entry"):
        _validate_axes({"v0": [0.8]}, {})


def test_validate_axes_rejects_extra_apply():
    with pytest.raises(ValueError, match="not declared"):
        _validate_axes({}, {"v0": lambda s, v: None})


def test_validate_axes_rejects_empty_axis_values():
    with pytest.raises(ValueError, match="no values"):
        _validate_axes({"v0": []}, {"v0": lambda s, v: None})


def test_sweep_result_to_dataframe_shape():
    pytest.importorskip("pandas")
    trials = [
        Trial(
            index=i,
            axis_values={"v0": v},
            seed=42,
            result=ScenarioResult(
                metrics={
                    "success": True,
                    "evacuation_time": 10.0 + i,
                    "total_agents": 5,
                    "agents_evacuated": 5,
                    "agents_remaining": 0,
                    "seed": 42,
                },
                sqlite_file=None,
            ),
        )
        for i, v in enumerate([0.8, 1.2, 1.6])
    ]
    sweep = SweepResult(trials=trials, axes={"v0": [0.8, 1.2, 1.6]}, seeds=[42])
    df = sweep.to_dataframe()

    assert list(df.columns) == [
        "v0",
        "seed",
        "trial_index",
        "success",
        "evacuation_time",
        "total_agents",
        "agents_evacuated",
        "agents_remaining",
        "sqlite_path",
    ]
    assert len(df) == 3
    assert df["v0"].tolist() == [0.8, 1.2, 1.6]
    assert df["success"].all()


def test_sweep_result_save_roundtrip(tmp_path):
    trials = [
        Trial(
            index=0,
            axis_values={"v0": 1.2},
            seed=7,
            result=ScenarioResult(metrics={"seed": 7, "success": True}, sqlite_file=None),
        )
    ]
    sweep = SweepResult(trials=trials, axes={"v0": [1.2]}, seeds=[7])
    out = tmp_path / "sweep.json"
    sweep.save(out)
    data = json.loads(out.read_text())
    assert data["axes"] == {"v0": [1.2]}
    assert data["seeds"] == [7]
    assert data["trials"][0]["axis_values"] == {"v0": 1.2}


def test_workers_negative_raises(corridor_scenario):
    with pytest.raises(ValueError, match="workers must be >= 0"):
        run_sweep(corridor_scenario, workers=-1)


def test_run_sweep_parallel_matches_sequential(corridor_scenario, tmp_path):
    """Two-worker run produces the same per-trial outcomes as the sequential path."""
    seq = run_sweep(
        corridor_scenario,
        seeds=[1, 2, 3],
        output_dir=tmp_path / "seq",
        workers=1,
    )
    par = run_sweep(
        corridor_scenario,
        seeds=[1, 2, 3],
        output_dir=tmp_path / "par",
        workers=2,
    )
    try:
        # Both runs return trials in plan order, indexed identically.
        assert [t.index for t in seq.trials] == [0, 1, 2]
        assert [t.index for t in par.trials] == [0, 1, 2]
        # Determinism check: same seed → same evacuation_time on a deterministic scenario.
        seq_times = [t.result.evacuation_time for t in seq.trials]
        par_times = [t.result.evacuation_time for t in par.trials]
        assert seq_times == par_times
    finally:
        seq.cleanup()
        par.cleanup()


# --- end-to-end ------------------------------------------------------------


def test_run_sweep_seed_only_replicates(corridor_scenario, tmp_path):
    sweep = run_sweep(corridor_scenario, seeds=[1, 2, 3], output_dir=tmp_path)

    assert len(sweep) == 3
    seen_seeds = [t.seed for t in sweep.trials]
    assert seen_seeds == [1, 2, 3]
    sqlite_paths = [pathlib.Path(t.result.sqlite_file) for t in sweep.trials]
    for t, p in zip(sweep.trials, sqlite_paths, strict=True):
        assert t.success, t.result.metrics.get("message")
        assert p.exists()

    sweep.cleanup()
    for p in sqlite_paths:
        assert not p.exists()


def test_run_sweep_axis_isolation(corridor_scenario, tmp_path):
    """Mutations to one trial's scenario copy must not leak to other trials."""
    dist_id = next(iter(corridor_scenario.distributions))

    def _count(scenario) -> int:
        return scenario.distributions[dist_id]["parameters"]["number"]

    original_count = _count(corridor_scenario)
    seen_counts: list[int] = []

    def apply_count(scenario, value):
        # Each trial's scenario must start at the base count — confirms .copy() isolation.
        seen_counts.append(_count(scenario))
        scenario.set_agent_count(dist_id, value)

    sweep = run_sweep(
        corridor_scenario,
        axes={"count": [original_count, original_count + 1]},
        apply={"count": apply_count},
        seeds=[42],
        output_dir=tmp_path,
    )

    assert seen_counts == [original_count, original_count]
    assert _count(corridor_scenario) == original_count
    assert len(sweep) == 2
    sweep.cleanup()
