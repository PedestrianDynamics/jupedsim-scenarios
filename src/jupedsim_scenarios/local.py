"""Seed sweep of one scenario into an output directory.

:func:`run_local` is the library form of ``jps-scenarios sweep``: it
loads the scenario, optionally scales it, runs every seed, and writes
``scenario.json`` plus ``sweep.json`` next to the trial sqlites. It
prints nothing; callers render ``progress`` themselves. The exported
``run.py`` of the web app and the CLI both go through it so the output
layout is defined once, and :func:`report.build_report` reads it back.
"""

from __future__ import annotations

import os
import pathlib
import time
from collections.abc import Callable, Sequence

try:
    from importlib.metadata import version as _pkg_version

    _VERSION = _pkg_version("jupedsim-scenarios")
except Exception:  # pragma: no cover - importlib.metadata failure is benign for --version
    _VERSION = "0.0.0"

from .runner import Scenario, load_scenario, save_scenario
from .sweep import SweepResult, run_sweep


def run_local(
    scenario: Scenario | str | os.PathLike,
    *,
    out_dir: str | os.PathLike,
    seeds: Sequence[int] | int = 10,
    workers: int = 1,
    dt: float | None = None,
    every_nth_frame: int = 10,
    scale: float = 1.0,
    scale_mode: str = "count",
    progress: Callable[[int, int, dict], None] | None = None,
) -> SweepResult:
    """Run ``scenario`` over ``seeds`` and save the sweep under ``out_dir``.

    Parameters
    ----------
    scenario
        A loaded :class:`Scenario` or anything :func:`load_scenario`
        accepts (JSON file, ZIP archive, directory). A loaded scenario
        is scaled in place when ``scale != 1.0``.
    out_dir
        Output directory: ``trial_<index>.sqlite`` per seed,
        ``scenario.json`` (the scenario as run) and ``sweep.json``.
    seeds
        Explicit seeds, or an int ``N`` meaning ``range(N)``.
    workers, dt, every_nth_frame, progress
        Passed through to :func:`run_sweep`.
    scale, scale_mode
        Passed to :meth:`Scenario.scale_agents` when ``scale != 1.0``;
        :class:`CapacityError` propagates.

    Returns
    -------
    SweepResult
        With ``meta`` filled in (``scenario_source``, ``scenario_json``,
        ``scale``, ``scale_mode``, ``seeds``, ``dt``, ``every_nth_frame``,
        ``wall_clock_s``, ``library_version``), already saved to
        ``out_dir / "sweep.json"``.
    """
    if isinstance(scenario, Scenario):
        source = scenario.source_path
    else:
        source = str(scenario)
        scenario = load_scenario(source)
    seeds_list = list(range(seeds)) if isinstance(seeds, int) else list(seeds)
    if scale != 1.0:
        scenario.scale_agents(scale, mode=scale_mode)

    out_path = pathlib.Path(out_dir)
    started = time.perf_counter()
    sweep = run_sweep(
        scenario,
        seeds=seeds_list,
        output_dir=out_path,
        workers=workers,
        progress=progress,
        dt=dt,
        every_nth_frame=every_nth_frame,
    )
    save_scenario(scenario, out_path / "scenario.json")
    wall_clock = round(time.perf_counter() - started, 3)

    sweep.meta.update(
        {
            "scenario_source": source,
            "scenario_json": "scenario.json",
            "scale": scale,
            "scale_mode": scale_mode,
            "seeds": seeds_list,
            "dt": dt,
            "every_nth_frame": every_nth_frame,
            "wall_clock_s": wall_clock,
            "library_version": _VERSION,
        }
    )
    sweep.save(out_path / "sweep.json")
    return sweep
