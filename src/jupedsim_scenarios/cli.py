"""Command-line entry point for jupedsim-scenarios.

    jps-scenarios run scenario.json --seed 42 --out trajectory.sqlite

Designed for CI smoke tests and scripted pipelines. Notebook use should
go through the Python API (`run_scenario` / `run_sweep`).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

try:
    from importlib.metadata import version as _pkg_version

    _VERSION = _pkg_version("jupedsim-scenarios")
except Exception:  # pragma: no cover - importlib.metadata failure is benign for --version
    _VERSION = "0.0.0"

from .runner import Scenario, run_scenario


def _build_scenario_from_json(path: pathlib.Path) -> Scenario:
    """Construct a Scenario from a single self-contained JSON file.

    Mirrors the constructor flow used in tests and the web app — the JSON
    is expected to embed `walkable_area_wkt` and a `config` block. For
    zipped exports (separate JSON + WKT) use `load_scenario` from Python
    instead.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if "walkable_area_wkt" not in data:
        raise SystemExit(
            f"{path}: missing 'walkable_area_wkt' — the CLI only accepts "
            "self-contained JSON. Use the Python API's load_scenario() "
            "for zipped exports."
        )
    sim_settings = data.get("config", {}).get("simulation_settings", {})
    sim_params = dict(sim_settings.get("simulationParams", {}))
    sim_params.setdefault("max_simulation_time", 300)
    return Scenario(
        raw=data,
        walkable_area_wkt=data["walkable_area_wkt"],
        model_type=sim_params.get(
            "model_type", data.get("model_type", "CollisionFreeSpeedModel")
        ),
        seed=data.get("seed", sim_settings.get("baseSeed", 42)),
        sim_params=sim_params,
        source_path=str(path),
    )


def _cmd_run(args: argparse.Namespace) -> int:
    scenario_path = pathlib.Path(args.scenario).resolve()
    if not scenario_path.exists():
        print(f"error: scenario file not found: {scenario_path}", file=sys.stderr)
        return 2

    scenario = _build_scenario_from_json(scenario_path)
    result = run_scenario(scenario, seed=args.seed)
    # `keep_sqlite` is only true once the trajectory has been moved to --out.
    # On the failure path the temp sqlite always gets cleaned, even if --out
    # was requested — otherwise we'd leak a tempfile the caller can't find.
    keep_sqlite = False
    try:
        if not result.success:
            print(
                f"error: simulation failed: {result.metrics.get('message', 'unknown')}",
                file=sys.stderr,
            )
            return 1

        if args.out and result.sqlite_file:
            target = pathlib.Path(args.out).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(result.sqlite_file, target)
            result.sqlite_file = str(target)
            keep_sqlite = True

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jps-scenarios",
        description="Run JuPedSim scenarios authored in the web app.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run a single scenario and emit a trajectory sqlite.")
    run.add_argument("scenario", help="Path to scenario JSON.")
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
    run.set_defaults(func=_cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - argparse entrypoint
    raise SystemExit(main())
