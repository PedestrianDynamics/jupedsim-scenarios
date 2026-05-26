"""Monte Carlo sweep over scenario parameters and seeds.

`run_sweep` walks the cartesian product of one or more named *axes* and
runs the scenario once per (axis-combination, seed) trial. Per-axis
mutations are applied via user-supplied callables so the sweep doesn't
need to know about the scenario's internal mutator surface — anything
that mutates the scenario in place works:

    sweep = run_sweep(
        base,
        axes={"v0": [0.8, 1.2], "model": ["CollisionFreeSpeedModel"]},
        apply={
            "v0":    lambda s, v: s.set_agent_params(0, desired_speed=v),
            "model": lambda s, v: s.set_model_type(v),
        },
        seeds=range(40, 50),
    )
    df = sweep.to_dataframe()    # one row per trial; axis values + metrics

The library owns: cartesian product, seed iteration, per-trial scenario
isolation (`.copy()` per trial), per-trial sqlite output naming, and
result tabulation.

Set ``workers=N`` (or ``workers=0`` for one process per CPU) to run trials
in parallel via ``joblib.Parallel`` (loky backend). Mutations are applied
in the *parent* process so user-supplied ``apply`` callables don't need
any special pickling treatment — only the resulting mutated ``Scenario``
crosses the process boundary.
"""

from __future__ import annotations

import itertools
import json
import os
import pathlib
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from joblib import Parallel, delayed

from .runner import Scenario, ScenarioResult, run_scenario

# A per-axis mutator: receives the trial's Scenario copy and the axis value,
# returns nothing. Side-effect only — mutates the scenario in place.
AxisApplyFn = Callable[[Scenario, Any], None]


@dataclass
class Trial:
    """One realised cell of the sweep: axis values + seed + result.

    `extras` is an opaque per-trial payload. `run_sweep` always leaves it
    `None`; `run_sweep_from_factory` lets the factory attach anything it
    likes (geometry, label, computed metadata) so downstream code can
    pick it up via `for t in sweep.trials: t.extras`.
    """

    index: int
    axis_values: dict[str, Any]
    seed: int
    result: ScenarioResult
    extras: Any = None

    @property
    def success(self) -> bool:
        return self.result.success


@dataclass
class SweepResult:
    """Collection of trials produced by `run_sweep`.

    Holds the per-trial `ScenarioResult` objects (each pointing at its own
    on-disk sqlite). Call `.cleanup()` when done to delete the sqlites,
    or `.save(path)` first if you want to keep the metadata.
    """

    trials: list[Trial]
    axes: dict[str, list[Any]] = field(default_factory=dict)
    seeds: list[int | None] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.trials)

    def __iter__(self):
        return iter(self.trials)

    def to_dataframe(self):
        """Return a pandas DataFrame with one row per trial.

        Columns: every axis name, ``seed``, ``success``, ``evacuation_time``,
        ``total_agents``, ``agents_evacuated``, ``agents_remaining``,
        ``sqlite_path``.
        """
        import pandas as pd

        rows = []
        for t in self.trials:
            row = dict(t.axis_values)
            row["seed"] = t.seed
            row["trial_index"] = t.index
            row["success"] = t.result.success
            row["evacuation_time"] = t.result.evacuation_time
            row["total_agents"] = t.result.total_agents
            row["agents_evacuated"] = t.result.agents_evacuated
            row["agents_remaining"] = t.result.agents_remaining
            row["sqlite_path"] = t.result.sqlite_file
            rows.append(row)
        return pd.DataFrame(rows)

    def cleanup(self) -> int:
        """Remove every trial's sqlite trajectory file.

        Returns the number of files actually removed (trials whose
        sqlite was already deleted or moved don't count).
        """
        return sum(t.result.cleanup() for t in self.trials)

    def save(self, path: str | pathlib.Path) -> None:
        """Persist sweep metadata (axes, seeds, per-trial paths + metrics) as JSON.

        The trajectory sqlites themselves are NOT moved — they stay where
        `run_sweep`'s `output_dir` put them. `load()` reattaches metadata to
        the sqlite files; if the sqlites are gone, the loaded result is
        metadata-only.
        """
        data = {
            "axes": {k: list(v) for k, v in self.axes.items()},
            "seeds": list(self.seeds),
            "trials": [
                {
                    "index": t.index,
                    "axis_values": t.axis_values,
                    "seed": t.seed,
                    "sqlite_path": t.result.sqlite_file,
                    "metrics": dict(t.result.metrics),
                }
                for t in self.trials
            ],
        }
        pathlib.Path(path).write_text(json.dumps(data, indent=2, default=str))


def _validate_axes(
    axes: Mapping[str, Sequence[Any]],
    apply: Mapping[str, AxisApplyFn],
) -> None:
    missing = set(axes) - set(apply)
    if missing:
        raise ValueError(
            f"Axes without an entry in `apply`: {sorted(missing)}. "
            "Every axis must have an apply function."
        )
    extra = set(apply) - set(axes)
    if extra:
        raise ValueError(
            f"`apply` has entries for axes not declared in `axes`: {sorted(extra)}."
        )
    for name, values in axes.items():
        if len(list(values)) == 0:
            raise ValueError(f"Axis {name!r} has no values.")


def _iter_axis_combinations(axes: Mapping[str, Sequence[Any]]):
    if not axes:
        yield {}
        return
    names = list(axes)
    value_lists = [list(axes[n]) for n in names]
    for combo in itertools.product(*value_lists):
        yield dict(zip(names, combo, strict=True))


def run_sweep(
    scenario: Scenario,
    *,
    axes: Mapping[str, Sequence[Any]] | None = None,
    apply: Mapping[str, AxisApplyFn] | None = None,
    seeds: Iterable[int | None] = (None,),
    output_dir: str | pathlib.Path | None = None,
    workers: int = 1,
    progress: Callable[[int, int, dict], None] | None = None,
) -> SweepResult:
    """Run the scenario once per (axis combination, seed) pair.

    Parameters
    ----------
    scenario
        The base scenario. ``.copy()`` is taken per trial; the caller's
        scenario is never mutated.
    axes
        Mapping of axis name → list of values. Trials cover the full
        cartesian product. Empty / None ⇒ no parameter sweep (seed-only).
    apply
        Mapping of axis name → callable ``(Scenario, value) -> None``.
        Mutates the trial's scenario copy in place. Required for each
        axis in ``axes``.
    seeds
        Seeds to replicate every axis combination over. Default
        ``(None,)`` ⇒ one trial per combination with whatever seed the
        scenario carries.
    output_dir
        If given, every trial's sqlite trajectory is placed inside it
        with a deterministic name (``trial_<index>.sqlite``). If omitted,
        each trial gets its own tempfile (cleaned by ``SweepResult.cleanup``).
    workers
        Number of parallel worker processes. ``1`` runs sequentially in
        the calling process; ``>1`` dispatches trials via
        ``joblib.Parallel`` (loky backend); ``0`` selects
        ``os.cpu_count()``. Trial-level mutations are applied in the
        parent process, so user ``apply`` callables don't need any
        special pickling treatment.
    progress
        Optional callback invoked after each trial with
        ``(trial_index, total_trials, axis_values_with_seed)``.

    Returns
    -------
    SweepResult
    """
    if workers < 0:
        raise ValueError(f"workers must be >= 0 (0 = all CPUs), got {workers!r}")

    axes = dict(axes or {})
    apply = dict(apply or {})
    _validate_axes(axes, apply)

    seeds_list = list(seeds)
    if not seeds_list:
        raise ValueError("`seeds` must contain at least one value (use [None] for the scenario's own seed).")

    combinations = list(_iter_axis_combinations(axes))
    total = len(combinations) * len(seeds_list)

    out_dir: pathlib.Path | None = None
    if output_dir is not None:
        out_dir = pathlib.Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    # Build every trial's mutated scenario in the parent so user `apply`
    # callables don't need to survive pickling. Each entry carries
    # everything the worker needs except output placement (handled in parent).
    # NOTE: this materialises N deep-copied Scenarios up front. Fine for
    # sweeps in the dozens-to-hundreds range; if you're running tens of
    # thousands of trials and the geometry is heavy, watch memory and
    # consider running multiple smaller sweeps. Lazy plan generation is
    # tracked as a follow-up.
    plan: list[tuple[int, dict[str, Any], int | None, Scenario]] = []
    for trial_index, (combo, seed) in enumerate(
        (c, s) for c in combinations for s in seeds_list
    ):
        trial_scenario = scenario.copy()
        for name, value in combo.items():
            apply[name](trial_scenario, value)
        plan.append((trial_index, dict(combo), seed, trial_scenario))

    effective_workers = workers if workers > 0 else (os.cpu_count() or 1)
    use_parallel = effective_workers > 1 and len(plan) > 1

    if use_parallel:
        # Loky backend uses cloudpickle, so closures in user code pickle
        # cleanly even though we don't rely on that — only the mutated
        # Scenario crosses the boundary. return_as="list" preserves input
        # order, matching the sequential path.
        results = Parallel(n_jobs=effective_workers, backend="loky", return_as="list")(
            delayed(run_scenario)(sc, seed=seed) for (_idx, _combo, seed, sc) in plan
        )
    else:
        results = [run_scenario(sc, seed=seed) for (_idx, _combo, seed, sc) in plan]

    trials: list[Trial] = []
    for (trial_index, combo, seed, _sc), result in zip(plan, results, strict=True):
        if progress is not None:
            payload = dict(combo)
            payload["seed"] = seed
            progress(trial_index + 1, total, payload)
        if out_dir is not None and result.sqlite_file:
            target = out_dir / f"trial_{trial_index:05d}.sqlite"
            shutil.move(result.sqlite_file, target)
            result.sqlite_file = str(target)
        trials.append(
            Trial(
                index=trial_index,
                axis_values=combo,
                seed=seed if seed is not None else result.seed,
                result=result,
            )
        )

    return SweepResult(
        trials=trials,
        axes={k: list(v) for k, v in axes.items()},
        seeds=seeds_list,
    )


# ---------------------------------------------------------------------------
# Factory-style sweep
# ---------------------------------------------------------------------------
# A scenario factory takes a trial parameters mapping and returns either a
# fresh Scenario or a (Scenario, extras) tuple. `extras` is opaque to the
# library — geometry, labels, anything the caller wants to keep around
# next to the result.
ScenarioFactoryFn = Callable[[Mapping[str, Any]], "Scenario | tuple[Scenario, Any]"]


def _normalize_factory_return(returned: Any) -> tuple[Scenario, Any]:
    """Accept either a Scenario or a (Scenario, extras) tuple."""
    if isinstance(returned, tuple):
        if len(returned) != 2:
            raise ValueError(
                "scenario factory must return either a Scenario or a "
                f"(Scenario, extras) 2-tuple; got a tuple of length {len(returned)}"
            )
        scenario, extras = returned
    else:
        scenario, extras = returned, None
    if not isinstance(scenario, Scenario):
        raise TypeError(
            "scenario factory must return a Scenario (optionally paired "
            f"with an extras value); got {type(scenario).__name__}"
        )
    return scenario, extras


def run_sweep_from_factory(
    factory: ScenarioFactoryFn,
    *,
    trials: Iterable[Mapping[str, Any]],
    seeds: Iterable[int | None] = (None,),
    output_dir: str | pathlib.Path | None = None,
    workers: int = 1,
    progress: Callable[[int, int, dict], None] | None = None,
) -> SweepResult:
    """Run one simulation per (trial-params, seed) pair, building each
    scenario fresh via a user-supplied factory.

    Use this when the scenario can't be expressed as a single base
    mutated by axis values — typically because the geometry itself
    depends on trial parameters (e.g. a loop track whose radius scales
    with agent count). Each call to ``factory(trial_params)`` is
    expected to construct a fresh ``Scenario``.

    Parameters
    ----------
    factory
        Callable ``(trial_params) -> Scenario`` or
        ``(trial_params) -> (Scenario, extras)``. Called once per
        trial-parameters dict in the parent process; the resulting
        Scenario is then pickled to a worker for the actual simulation.
        ``extras`` (if returned) is attached to ``Trial.extras`` for the
        caller to read after the sweep completes.
    trials
        Iterable of trial-parameters mappings. The mapping's keys
        become the DataFrame columns when you call
        ``SweepResult.to_dataframe()``, so name them meaningfully.
    seeds
        Seeds to replicate every trial-params combination over.
        Default ``(None,)`` ⇒ one run per trial-params dict using the
        seed embedded in the factory's Scenario.
    output_dir, workers, progress
        Same semantics as ``run_sweep``.

    Returns
    -------
    SweepResult
    """
    if workers < 0:
        raise ValueError(f"workers must be >= 0 (0 = all CPUs), got {workers!r}")

    seeds_list = list(seeds)
    if not seeds_list:
        raise ValueError(
            "`seeds` must contain at least one value (use [None] for the "
            "scenario's own seed)."
        )

    trials_list = [dict(t) for t in trials]
    if not trials_list:
        raise ValueError("`trials` must contain at least one trial-parameters mapping.")

    out_dir: pathlib.Path | None = None
    if output_dir is not None:
        out_dir = pathlib.Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    # Materialise every trial's Scenario in the parent. Same memory-vs-
    # latency tradeoff as run_sweep (see note in run_sweep); lazy
    # construction is a follow-up.
    plan: list[tuple[int, dict[str, Any], int | None, Scenario, Any]] = []
    for trial_index, (trial_params, seed) in enumerate(
        (t, s) for t in trials_list for s in seeds_list
    ):
        scenario, extras = _normalize_factory_return(factory(trial_params))
        plan.append((trial_index, trial_params, seed, scenario, extras))

    total = len(plan)
    effective_workers = workers if workers > 0 else (os.cpu_count() or 1)
    use_parallel = effective_workers > 1 and total > 1

    if use_parallel:
        results = Parallel(n_jobs=effective_workers, backend="loky", return_as="list")(
            delayed(run_scenario)(sc, seed=seed)
            for (_idx, _params, seed, sc, _extras) in plan
        )
    else:
        results = [
            run_scenario(sc, seed=seed)
            for (_idx, _params, seed, sc, _extras) in plan
        ]

    out_trials: list[Trial] = []
    for (trial_index, trial_params, seed, _sc, extras), result in zip(
        plan, results, strict=True
    ):
        if progress is not None:
            payload = dict(trial_params)
            payload["seed"] = seed
            progress(trial_index + 1, total, payload)
        if out_dir is not None and result.sqlite_file:
            target = out_dir / f"trial_{trial_index:05d}.sqlite"
            shutil.move(result.sqlite_file, target)
            result.sqlite_file = str(target)
        out_trials.append(
            Trial(
                index=trial_index,
                axis_values=trial_params,
                seed=seed if seed is not None else result.seed,
                result=result,
                extras=extras,
            )
        )

    # Reconstruct an axis-name → distinct-values map from the trial-params
    # dicts for SweepResult.axes (matches what run_sweep stores). Insertion
    # order is preserved on both the keys and their value lists.
    axes_summary: dict[str, list[Any]] = {}
    for t in trials_list:
        for k, v in t.items():
            bucket = axes_summary.setdefault(k, [])
            if v not in bucket:
                bucket.append(v)

    return SweepResult(
        trials=out_trials,
        axes=axes_summary,
        seeds=seeds_list,
    )
