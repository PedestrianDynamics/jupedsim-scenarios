"""Tests for run_sweep_from_factory (#11).

Pure-logic cases run without jupedsim — they exercise the factory-return
normalisation, axis reconstruction, error paths, and Trial.extras
plumbing using a stub Scenario. The one end-to-end test loads the
corridor fixture, builds a tiny per-trial mutator-via-factory pattern,
and confirms the run completes.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest

from jupedsim_scenarios.runner import Scenario
from jupedsim_scenarios.sweep import _normalize_factory_return, run_sweep_from_factory

# --- pure-logic ------------------------------------------------------------


def _stub_scenario() -> Scenario:
    """Build a minimal Scenario without touching jupedsim."""
    return Scenario(
        raw={},
        walkable_area_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        model_type="CollisionFreeSpeedModel",
        seed=0,
        sim_params={},
        source_path="stub",
    )


def test_normalize_factory_return_accepts_bare_scenario():
    s = _stub_scenario()
    scenario, extras = _normalize_factory_return(s)
    assert scenario is s
    assert extras is None


def test_normalize_factory_return_accepts_scenario_with_extras():
    s = _stub_scenario()
    payload = {"label": "loop-1", "track_length": 12.5}
    scenario, extras = _normalize_factory_return((s, payload))
    assert scenario is s
    assert extras is payload


def test_normalize_factory_return_rejects_wrong_tuple_arity():
    s = _stub_scenario()
    with pytest.raises(ValueError, match="2-tuple"):
        _normalize_factory_return((s, "a", "b"))


def test_normalize_factory_return_rejects_non_scenario():
    with pytest.raises(TypeError, match="must return a Scenario"):
        _normalize_factory_return("not a scenario")


def test_run_sweep_from_factory_rejects_empty_trials():
    with pytest.raises(ValueError, match="at least one trial-parameters"):
        run_sweep_from_factory(lambda _: _stub_scenario(), trials=[])


def test_run_sweep_from_factory_rejects_negative_workers():
    with pytest.raises(ValueError, match="workers must be >= 0"):
        run_sweep_from_factory(
            lambda _: _stub_scenario(),
            trials=[{"n": 1}],
            workers=-1,
        )


# --- end-to-end ------------------------------------------------------------


def test_run_sweep_from_factory_dataframe_and_extras(corridor_scenario, tmp_path):
    """Factory builds a fresh Scenario per trial, optionally returning a
    payload. End-to-end check: every trial runs, axis_values populate
    the DataFrame, extras flow back on Trial."""
    pytest.importorskip("pandas")

    @dataclass
    class _Label:
        text: str

    def factory(params):
        scenario = corridor_scenario.copy()
        dist_id = next(iter(scenario.distributions))
        scenario.set_agent_count(dist_id, params["n_agents"])
        return scenario, _Label(text=f"trial-{params['n_agents']}")

    sweep = run_sweep_from_factory(
        factory,
        trials=[{"n_agents": 5}, {"n_agents": 7}],
        seeds=[42],
        output_dir=tmp_path,
        workers=1,
    )

    assert len(sweep) == 2
    df = sweep.to_dataframe()
    assert list(df["n_agents"]) == [5, 7]
    assert all(t.result.success for t in sweep.trials), [
        t.result.metrics.get("message") for t in sweep.trials
    ]
    assert all(isinstance(t.extras, _Label) for t in sweep.trials)
    assert sweep.trials[0].extras.text == "trial-5"
    assert sweep.trials[1].extras.text == "trial-7"

    sweep.cleanup()
    for t in sweep.trials:
        assert not pathlib.Path(t.result.sqlite_file or "/nonexistent").exists()
