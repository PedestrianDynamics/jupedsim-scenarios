"""High-level API for loading, building, running, and persisting
JuPedSim scenarios.

The package wraps the lower-level :mod:`jupedsim.Simulation` primitives
into a load → mutate → run → analyse flow that matches what
scientists building and sweeping scenarios actually want.

The :command:`jps-scenarios` CLI (entry point :func:`cli.main`)
exposes the same surface for scripted pipelines.
"""

from .runner import (
    Scenario,
    ScenarioResult,
    ScenarioRunner,
    load_scenario,
    run_scenario,
    save_scenario,
)
from .sweep import SweepResult, Trial, run_sweep, run_sweep_from_factory

__all__ = [
    "Scenario",
    "ScenarioResult",
    "ScenarioRunner",
    "SweepResult",
    "Trial",
    "load_scenario",
    "run_scenario",
    "run_sweep",
    "run_sweep_from_factory",
    "save_scenario",
]
