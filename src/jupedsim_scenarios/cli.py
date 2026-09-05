"""Command-line entry point for jupedsim-scenarios.

    jps-scenarios run scenario.json --seed 42 --out trajectory.sqlite
    jps-scenarios run scenario.zip --out trajectory.sqlite
    jps-scenarios run scenario_dir/ --out trajectory.sqlite
    jps-scenarios sweep scenario.zip --seeds 20 --scale 10 --workers 4 --out results/
    jps-scenarios report results/ --out report.html

Accepts the same inputs as ``load_scenario`` — single self-contained
JSON, ZIP archive, or a directory holding ``*.json`` + ``*.wkt``.
Designed for CI smoke tests and scripted pipelines. Notebook use should
go through the Python API (``run_scenario`` / ``run_sweep``).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

try:
    from importlib.metadata import version as _pkg_version

    _VERSION = _pkg_version("jupedsim-scenarios")
except Exception:  # pragma: no cover - importlib.metadata failure is benign for --version
    _VERSION = "0.0.0"

from ._quiet import request_quiet
from .runner import CapacityError, load_scenario, run_scenario, save_scenario
from .sweep import run_sweep

SCENARIO_HELP = (
    "Scenario source: a self-contained JSON file, a ZIP archive, "
    "or a directory holding one JSON + one WKT."
)


def _cmd_run(args: argparse.Namespace) -> int:
    scenario_path = pathlib.Path(args.scenario).resolve()
    if not scenario_path.exists():
        print(f"error: scenario path not found: {scenario_path}", file=sys.stderr)
        return 2

    try:
        scenario = load_scenario(str(scenario_path))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        result = run_scenario(
            scenario,
            seed=args.seed,
            dt=args.dt,
            every_nth_frame=args.every_nth_frame,
            output_path=args.out,
        )
    # Either invalid args (ValueError) or filesystem trouble writing the
    # trajectory (OSError / PermissionError on parent.mkdir / sqlite open)
    # surface as a friendly exit-2 instead of a traceback.
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Keep the sqlite only when --out was given AND the run succeeded.
    # On the failure path with --out, clean up so we don't leave a
    # partial / misleading trajectory at a known location.
    keep_sqlite = args.out is not None and result.success
    try:
        if not result.success:
            print(
                f"error: simulation failed: {result.metrics.get('message', 'unknown')}",
                file=sys.stderr,
            )
            return 1

        summary = {
            "scenario": str(scenario_path),
            "seed": result.seed,
            "model_type": scenario.model_type,
            "evacuation_time": result.evacuation_time,
            "total_agents": result.total_agents,
            "agents_evacuated": result.agents_evacuated,
            "agents_remaining": result.agents_remaining,
            # Only report the sqlite path when we're actually keeping the file
            # (i.e. --out was given). Otherwise it's about to be unlinked.
            "sqlite_file": result.sqlite_file if keep_sqlite else None,
        }
        # Single-line JSON so callers (CI, scripts) can grep the last line of
        # stdout without colliding with the simulation engine's DEBUG prints.
        print(json.dumps(summary))
        return 0
    finally:
        if not keep_sqlite:
            result.cleanup()


def _sweep_seeds(args: argparse.Namespace) -> list[int]:
    if args.seed_start is not None or args.seed_end is not None:
        if args.seed_start is None or args.seed_end is None:
            raise ValueError("--seed-start and --seed-end must be given together")
        if args.seed_end < args.seed_start:
            raise ValueError("--seed-end must be >= --seed-start")
        return list(range(args.seed_start, args.seed_end + 1))
    if args.seeds < 1:
        raise ValueError("--seeds must be >= 1")
    return list(range(args.seeds))


def _cmd_sweep(args: argparse.Namespace) -> int:
    scenario_path = pathlib.Path(args.scenario).resolve()
    if not scenario_path.exists():
        print(f"error: scenario path not found: {scenario_path}", file=sys.stderr)
        return 2
    try:
        seeds = _sweep_seeds(args)
        scenario = load_scenario(str(scenario_path))
        scenario.scale_agents(args.scale, mode=args.scale_mode)
    except CapacityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_dir = pathlib.Path(args.out)

    def _progress(done: int, total: int, payload: dict) -> None:
        print(f"trial {done}/{total} seed={payload.get('seed')}", flush=True)

    started = time.perf_counter()
    try:
        sweep = run_sweep(
            scenario,
            seeds=seeds,
            output_dir=out_dir,
            workers=args.workers,
            progress=_progress,
            dt=args.dt,
            every_nth_frame=args.every_nth_frame,
        )
        save_scenario(scenario, out_dir / "scenario.json")
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    wall_clock = round(time.perf_counter() - started, 3)

    sweep.meta.update(
        {
            "scenario_source": str(scenario_path),
            "scenario_json": "scenario.json",
            "scale": args.scale,
            "scale_mode": args.scale_mode,
            "seeds": seeds,
            "dt": args.dt,
            "every_nth_frame": args.every_nth_frame,
            "wall_clock_s": wall_clock,
            "library_version": _VERSION,
        }
    )
    sweep.save(out_dir / "sweep.json")

    n_failed = sum(not t.result.success for t in sweep.trials)
    summary = {
        "n_trials": len(sweep.trials),
        "n_failed": n_failed,
        "scale": args.scale,
        "mode": args.scale_mode,
        "seeds": seeds,
        "wall_clock_s": wall_clock,
        "out": str(out_dir),
    }
    print(json.dumps(summary))
    return 1 if n_failed == len(sweep.trials) else 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .report import build_report

    results_dir = pathlib.Path(args.results_dir)
    if not results_dir.exists():
        print(f"error: results dir not found: {results_dir}", file=sys.stderr)
        return 2
    try:
        out = build_report(results_dir, args.out, playback=args.playback)
    except (ImportError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"report": str(out)}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jps-scenarios",
        description="Run JuPedSim scenarios authored in the web app.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show the library's INFO log lines (hidden by default, also in sweep workers).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a single scenario and emit a trajectory sqlite.")
    run.add_argument("scenario", help=SCENARIO_HELP)
    run.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Override the scenario's seed (default: use the value in the JSON).",
    )
    run.add_argument(
        "--out",
        default=None,
        help="Where to write the trajectory sqlite. If omitted, the file is "
        "created in a tempdir and deleted on exit (metrics are still printed).",
    )
    run.add_argument(
        "--dt",
        type=float,
        default=None,
        help="Iteration step in seconds (default: the scenario's simulationParams.dt, "
        "else jupedsim's built-in 0.01).",
    )
    run.add_argument(
        "--every-nth-frame",
        type=int,
        default=10,
        help="Trajectory writer stride. Default 10 (≈ 10 fps at dt=0.01); "
        "set to 1 to capture every iteration.",
    )
    run.set_defaults(func=_cmd_run)

    sweep = sub.add_parser(
        "sweep",
        help="Run a scenario over many seeds, optionally scaled up, into an output directory.",
    )
    sweep.add_argument("scenario", help=SCENARIO_HELP)
    seed_group = sweep.add_mutually_exclusive_group()
    seed_group.add_argument(
        "--seeds", type=int, default=1, help="Number of seeds, 0..N-1 (default 1)."
    )
    seed_group.add_argument(
        "--seed-start", type=int, default=None, help="First seed (use with --seed-end)."
    )
    sweep.add_argument(
        "--seed-end", type=int, default=None, help="Last seed, inclusive (use with --seed-start)."
    )
    sweep.add_argument(
        "--scale", type=float, default=1.0, help="Agent scaling factor (default 1.0)."
    )
    sweep.add_argument(
        "--scale-mode",
        choices=("count", "flow"),
        default="count",
        help="count: multiply start-area counts (refuses on capacity overflow, checked "
        "with the scenario's base seed; a seed that still cannot place the agents is "
        "recorded as a failed trial); "
        "flow: keep the spawn rate and stretch flow windows (needs flow spawning).",
    )
    sweep.add_argument(
        "--workers", type=int, default=1, help="Parallel worker processes (0 = all CPUs)."
    )
    sweep.add_argument("--out", required=True, help="Output directory for sqlites and sweep.json.")
    sweep.add_argument(
        "--dt",
        type=float,
        default=None,
        help="Iteration step in seconds (default: the scenario's simulationParams.dt, "
        "else jupedsim's built-in).",
    )
    sweep.add_argument(
        "--every-nth-frame",
        type=int,
        default=10,
        help="Trajectory writer stride. Default 10, matching `run`.",
    )
    sweep.set_defaults(func=_cmd_sweep)

    report = sub.add_parser("report", help="Render a saved sweep as a self-contained HTML report.")
    report.add_argument("results_dir", help="Directory written by `jps-scenarios sweep --out`.")
    report.add_argument("--out", default=None, help="Report path (default <results_dir>/report.html).")
    report.add_argument(
        "--playback",
        action="store_true",
        help="Also write per-trial plotly playback files next to the report (large).",
    )
    report.set_defaults(func=_cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    request_quiet(not args.verbose)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - argparse entrypoint
    raise SystemExit(main())
