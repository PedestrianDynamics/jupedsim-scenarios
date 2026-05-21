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

Parallel execution is deferred to a follow-up — `workers` is accepted as
a parameter today but only `workers=1` (sequential) is implemented.
That keeps the public API stable for the multiprocess work later.
"""

from __future__ import annotations

import itertools
import json
import pathlib
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .runner import Scenario, ScenarioResult, run_scenario

# A per-axis mutator: receives the trial's Scenario copy and the axis value,
# returns nothing. Side-effect only — mutates the scenario in place.
AxisApplyFn = Callable[[Scenario, Any], None]


@dataclass
class Trial:
    """One realised cell of the sweep: axis values + seed + result."""

    index: int
    axis_values: dict[str, Any]
    seed: int
    result: ScenarioResult

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

    def cleanup(self) -> None:
        """Remove every trial's sqlite trajectory file."""
        for t in self.trials:
            t.result.cleanup()

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
        Reserved for the multiprocess implementation. Only ``workers=1``
        (sequential) is supported in this release; any other value raises
        ``NotImplementedError``.
    progress
        Optional callback invoked after each trial with
        ``(trial_index, total_trials, axis_values_with_seed)``.

    Returns
    -------
    SweepResult
    """
    if workers != 1:
        raise NotImplementedError(
            "Parallel sweeps (workers > 1) are not yet implemented. "
            "Run sequentially with workers=1 for now; multiprocess support "
            "lands in a follow-up release."
        )

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

    trials: list[Trial] = []
    for trial_index, (combo, seed) in enumerate(
        (c, s) for c in combinations for s in seeds_list
    ):
        trial_scenario = scenario.copy()
        for name, value in combo.items():
            apply[name](trial_scenario, value)

        result = run_scenario(trial_scenario, seed=seed)
        if out_dir is not None and result.sqlite_file:
            target = out_dir / f"trial_{trial_index:05d}.sqlite"
            shutil.move(result.sqlite_file, target)
            result.sqlite_file = str(target)
        trials.append(
            Trial(
                index=trial_index,
                axis_values=dict(combo),
                seed=seed if seed is not None else result.seed,
                result=result,
            )
        )

        if progress is not None:
            payload = dict(combo)
            payload["seed"] = seed
            progress(trial_index + 1, total, payload)

    return SweepResult(
        trials=trials,
        axes={k: list(v) for k, v in axes.items()},
        seeds=seeds_list,
    )
