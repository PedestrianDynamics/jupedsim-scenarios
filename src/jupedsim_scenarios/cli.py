"""Command-line entry point for jupedsim-scenarios.

    jps-scenarios run scenario.json --seed 42 --out trajectory.sqlite
    jps-scenarios run scenario.zip --out trajectory.sqlite
    jps-scenarios run scenario_dir/ --out trajectory.sqlite

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

try:
    from importlib.metadata import version as _pkg_version

    _VERSION = _pkg_version("jupedsim-scenarios")
except Exception:  # pragma: no cover - importlib.metadata failure is benign for --version
    _VERSION = "0.0.0"

from .runner import load_scenario, run_scenario


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jps-scenarios",
        description="Run JuPedSim scenarios authored in the web app.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a single scenario and emit a trajectory sqlite.")
    run.add_argument(
        "scenario",
        help="Scenario source: a self-contained JSON file, a ZIP archive, "
        "or a directory holding one JSON + one WKT.",
    )
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
        help="Iteration step in seconds (default: jupedsim's built-in, "
        "currently 0.01).",
    )
    run.add_argument(
        "--every-nth-frame",
        type=int,
        default=10,
        help="Trajectory writer stride. Default 10 (≈ 10 fps at dt=0.01); "
        "set to 1 to capture every iteration.",
    )
    run.set_defaults(func=_cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - argparse entrypoint
    raise SystemExit(main())
