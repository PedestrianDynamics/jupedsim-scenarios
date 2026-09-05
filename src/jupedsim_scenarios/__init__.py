"""High-level API for loading, building, running, and persisting
JuPedSim scenarios.

The package wraps the lower-level :mod:`jupedsim.Simulation` primitives
into a load → mutate → run → analyse flow that matches what
scientists building and sweeping scenarios actually want.

The :command:`jps-scenarios` CLI (entry point :func:`cli.main`)
exposes the same surface for scripted pipelines.
"""

from .capacity import PRACTICAL_PACKING_FACTOR, max_agents_for_distribution
from .local import run_local
from .runner import (
    CapacityError,
    Scenario,
    ScenarioResult,
    ScenarioRunner,
    load_scenario,
    run_scenario,
    save_scenario,
)
from .sweep import SweepResult, Trial, run_sweep, run_sweep_from_factory


def scale_agents(scenario: Scenario, factor: float, *, mode: str = "count") -> None:
    """Function form of :meth:`Scenario.scale_agents` (mutates in place)."""
    scenario.scale_agents(factor, mode=mode)


__all__ = [
    "PRACTICAL_PACKING_FACTOR",
    "CapacityError",
    "Scenario",
    "ScenarioResult",
    "ScenarioRunner",
    "SweepResult",
    "Trial",
    "load_scenario",
    "max_agents_for_distribution",
    "run_local",
    "run_scenario",
    "run_sweep",
    "run_sweep_from_factory",
    "save_scenario",
    "scale_agents",
]
