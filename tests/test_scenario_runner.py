"""``ScenarioRunner`` interactive API (R2.5).

Drives a scenario tick-by-tick. ``run_scenario`` is now a thin wrapper
that runs to completion — these tests check the parts of the runner
the wrapper doesn't exercise: stepping, inspection between steps,
re-entering after mutation, and clean teardown.
"""

from __future__ import annotations

import pathlib

import pytest

from jupedsim_scenarios import ScenarioRunner


def test_run_until_partial_then_inspect(corridor_scenario):
    with ScenarioRunner(corridor_scenario, seed=42) as runner:
        runner.run_until(2.0)
        # run_until stops at the first tick where elapsed_time >= target,
        # so the actual time is in [target, target + dt).
        dt = runner.simulation.delta_time()
        assert 2.0 <= runner.elapsed_time < 2.0 + dt + 1e-9
        assert runner.agent_count > 0
        # Step a single iteration and check elapsed_time advances by dt.
        before = runner.elapsed_time
        runner.step()
        assert runner.elapsed_time == pytest.approx(before + dt, rel=1e-9)


def test_run_until_default_runs_to_completion(corridor_scenario):
    with ScenarioRunner(corridor_scenario, seed=42) as runner:
        runner.run_until()  # default = scenario.max_simulation_time
        result = runner.result()
        assert result.success
        assert result.agents_remaining == 0


def test_chained_run_until_advances_in_chunks(corridor_scenario):
    with ScenarioRunner(corridor_scenario, seed=42) as runner:
        runner.run_until(1.0)
        t1 = runner.elapsed_time
        runner.run_until(2.0)
        t2 = runner.elapsed_time
        runner.run_until(3.0)
        t3 = runner.elapsed_time
        assert t1 < t2 < t3
        dt = runner.simulation.delta_time()
        assert 3.0 <= t3 < 3.0 + dt + 1e-9


def test_result_callable_mid_run(corridor_scenario):
    with ScenarioRunner(corridor_scenario, seed=42) as runner:
        runner.run_until(1.0)
        mid = runner.result()
        # Mid-run: not yet succeeded.
        assert not mid.success
        # Calling result() doesn't terminate the simulation; we can keep going.
        runner.run_until()
        final = runner.result()
        assert final.success


def test_output_path_persists_after_close(corridor_scenario, tmp_path):
    target = tmp_path / "interactive.sqlite"
    with ScenarioRunner(corridor_scenario, seed=42, output_path=target) as runner:
        runner.run_until(1.0)
        result = runner.result()
        assert pathlib.Path(result.sqlite_file).resolve() == target.resolve()
    # Closing the runner closes the writer but keeps the file.
    assert target.exists()
    result.cleanup()


def test_close_is_idempotent(corridor_scenario):
    runner = ScenarioRunner(corridor_scenario, seed=42)
    runner.run_until(0.5)
    sqlite_path = runner.result().sqlite_file
    runner.close()
    runner.close()  # second close is a no-op
    # close() doesn't remove the trajectory file; clean it up so the
    # test suite doesn't leave tempfiles behind across runs.
    pathlib.Path(sqlite_path).unlink(missing_ok=True)


def test_step_after_close_raises(corridor_scenario):
    runner = ScenarioRunner(corridor_scenario, seed=42)
    sqlite_path = runner.result().sqlite_file
    runner.close()
    with pytest.raises(RuntimeError, match="closed"):
        runner.step()
    with pytest.raises(RuntimeError, match="closed"):
        runner.run_until(1.0)
    with pytest.raises(RuntimeError, match="closed"):
        runner.result()
    pathlib.Path(sqlite_path).unlink(missing_ok=True)


def test_run_until_zero_is_noop(corridor_scenario):
    with ScenarioRunner(corridor_scenario, seed=42) as runner:
        before = runner.elapsed_time
        runner.run_until(0.0)
        assert runner.elapsed_time == before


def test_run_until_past_max_simulation_time_is_clamped(corridor_scenario):
    # Setting max_simulation_time short and asking for more must NOT
    # drive the sim past the scenario's configured horizon.
    corridor_scenario.max_simulation_time = 1.0
    with ScenarioRunner(corridor_scenario, seed=42) as runner:
        runner.run_until(999.0)
        assert runner.elapsed_time <= 1.0 + runner.simulation.delta_time() + 1e-9


def test_exception_in_with_block_cleans_tempfile(corridor_scenario):
    sqlite_path = None
    with pytest.raises(RuntimeError, match="boom"):
        with ScenarioRunner(corridor_scenario, seed=42) as runner:
            runner.run_until(0.5)
            sqlite_path = runner.result().sqlite_file
            raise RuntimeError("boom")
    # The trajectory tempfile was removed on the exception path.
    assert sqlite_path is not None
    assert not pathlib.Path(sqlite_path).exists()


def test_explicit_output_path_kept_after_exception(corridor_scenario, tmp_path):
    target = tmp_path / "kept.sqlite"
    with pytest.raises(RuntimeError, match="boom"):
        with ScenarioRunner(corridor_scenario, seed=42, output_path=target) as runner:
            runner.run_until(0.5)
            raise RuntimeError("boom")
    # User-supplied output paths survive exceptions; the runner only
    # removes files it created itself.
    assert target.exists()
